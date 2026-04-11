from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base, CompanyAccount, Customer, CustomerTargetAccount, ExchangeRate, Order, Supplier
from app.services import get_balance, seed_default_rates


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    with TestingSessionLocal() as db:
        seed_default_rates(db)

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, TestingSessionLocal
    app.dependency_overrides.clear()


def test_entities_and_cash_order_flow(client):
    http, SessionLocal = client
    http.post("/customers", data={"name": "Alice", "contact": "wx-a"})
    http.post("/suppliers", data={"name": "Bob", "contact": "wx-b"})
    http.post(
        "/company-accounts",
        data={"name": "HSBC AUD", "bank_name": "HSBC", "account_no": "001", "primary_currency": "AUD"},
    )

    with SessionLocal() as db:
        customer = db.query(Customer).filter_by(name="Alice").one()
        supplier = db.query(Supplier).filter_by(name="Bob").one()
        account = db.query(CompanyAccount).filter_by(name="HSBC AUD").one()

    http.post(
        "/customer-target-accounts",
        data={
            "customer_id": customer.id,
            "account_name": "Alice Target",
            "bank_name": "CBA",
            "account_no": "888",
            "currency": "USD",
            "holder_name": "Alice",
        },
    )

    with SessionLocal() as db:
        target = db.query(CustomerTargetAccount).filter_by(account_name="Alice Target").one()

    http.post(
        "/orders/cash",
        data={
            "customer_id": customer.id,
            "supplier_id": supplier.id,
            "company_account_id": account.id,
            "target_account_id": target.id,
            "deposit_amount": "1000",
            "deposit_currency": "AUD",
            "payout_amount": "650",
            "payout_currency": "USD",
            "notes": "cash order",
        },
    )

    with SessionLocal() as db:
        order = db.query(Order).one()
        assert order.status == "待处理"
        assert get_balance(db, account.id, "AUD") == Decimal("0.00")

    http.post("/orders/1/advance")
    http.post("/orders/1/advance")

    with SessionLocal() as db:
        order = db.query(Order).one()
        assert order.status == "在公司账号"
        assert get_balance(db, account.id, "AUD") == Decimal("1000.00")

    http.post("/exchange", data={"company_account_id": account.id, "source_currency": "AUD", "source_amount": "1000", "target_currency": "USD"})

    with SessionLocal() as db:
        assert get_balance(db, account.id, "AUD") == Decimal("0.00")
        assert get_balance(db, account.id, "USD") == Decimal("650.00")

    http.post("/orders/1/advance")

    with SessionLocal() as db:
        order = db.query(Order).one()
        assert order.status == "已完成"
        assert get_balance(db, account.id, "USD") == Decimal("0.00")


def test_bank_order_and_rate_update(client):
    http, SessionLocal = client
    http.post("/customers", data={"name": "Carol", "contact": "wx-c"})
    http.post(
        "/company-accounts",
        data={"name": "CBA USD", "bank_name": "CBA", "account_no": "002", "primary_currency": "USD"},
    )

    with SessionLocal() as db:
        customer = db.query(Customer).filter_by(name="Carol").one()
        account = db.query(CompanyAccount).filter_by(name="CBA USD").one()

    http.post(
        "/customer-target-accounts",
        data={
            "customer_id": customer.id,
            "account_name": "Carol Target",
            "bank_name": "BOC",
            "account_no": "999",
            "currency": "USD",
            "holder_name": "Carol",
        },
    )

    with SessionLocal() as db:
        target = db.query(CustomerTargetAccount).filter_by(account_name="Carol Target").one()

    http.post(
        "/orders/bank-transfer",
        data={
            "customer_id": customer.id,
            "company_account_id": account.id,
            "target_account_id": target.id,
            "deposit_amount": "500",
            "deposit_currency": "USD",
            "payout_amount": "300",
            "payout_currency": "USD",
            "notes": "bank order",
        },
    )

    with SessionLocal() as db:
        order = db.query(Order).filter_by(customer_id=customer.id).one()
        assert order.status == "在公司账号"
        assert get_balance(db, account.id, "USD") == Decimal("500.00")

    http.post("/orders/1/advance")

    with SessionLocal() as db:
        order = db.query(Order).filter_by(customer_id=customer.id).one()
        assert order.status == "已完成"
        assert get_balance(db, account.id, "USD") == Decimal("200.00")

    http.post("/settings/rates", data={"currency": "USD", "rate_to_aud_base": "0.70"})

    with SessionLocal() as db:
        row = db.query(ExchangeRate).filter_by(currency="USD").one()
        assert Decimal(row.rate_to_aud_base) == Decimal("0.700000")


def test_order_can_be_created_without_target_account_and_completed_after_update(client):
    http, SessionLocal = client
    http.post("/customers", data={"name": "Sammer", "contact": "wx-s"})
    http.post("/suppliers", data={"name": "Bob", "contact": "wx-b"})
    http.post(
        "/company-accounts",
        data={"name": "HSBC AUD", "bank_name": "HSBC", "account_no": "001", "primary_currency": "AUD"},
    )

    with SessionLocal() as db:
        customer = db.query(Customer).filter_by(name="Sammer").one()
        supplier = db.query(Supplier).filter_by(name="Bob").one()
        account = db.query(CompanyAccount).filter_by(name="HSBC AUD").one()

    http.post(
        "/orders/cash",
        data={
            "customer_id": customer.id,
            "supplier_id": supplier.id,
            "company_account_id": account.id,
            "target_account_id": "",
            "deposit_amount": "1000",
            "deposit_currency": "AUD",
            "payout_amount": "",
            "payout_currency": "",
            "notes": "no target yet",
        },
    )

    with SessionLocal() as db:
        order = db.query(Order).one()
        assert order.target_account_id is None
        assert order.payout_amount is None
        assert order.payout_currency is None

    http.post("/orders/1/advance")
    http.post("/orders/1/advance")
    blocked = http.post("/orders/1/advance")
    assert blocked.status_code == 200

    http.post(
        "/customer-target-accounts",
        data={
            "customer_id": customer.id,
            "account_name": "Sammer USD",
            "bank_name": "CBA",
            "account_no": "ACC-100",
            "currency": "USD",
            "holder_name": "Sammer",
        },
    )

    with SessionLocal() as db:
        target = db.query(CustomerTargetAccount).filter_by(account_name="Sammer USD").one()

    http.post("/orders/1/payout", data={"payout_amount": "650", "payout_currency": "USD"})
    http.post("/orders/1/target-account", data={"target_account_id": target.id})
    http.post(
        "/exchange",
        data={
            "company_account_id": account.id,
            "source_currency": "AUD",
            "source_amount": "1000",
            "target_currency": "USD",
        },
    )
    http.post("/orders/1/advance")

    with SessionLocal() as db:
        order = db.query(Order).one()
        assert order.target_account_id == target.id
        assert Decimal(order.payout_amount) == Decimal("650.00")
        assert order.payout_currency == "USD"
        assert order.status == "已完成"


def test_sample_data_seed_route(client):
    http, SessionLocal = client

    first = http.post("/sample-data")
    assert first.status_code == 200

    with SessionLocal() as db:
        assert db.query(Customer).count() >= 3
        assert db.query(CompanyAccount).count() >= 2
        assert db.query(Order).count() >= 4

    second = http.post("/sample-data")
    assert second.status_code == 200

    with SessionLocal() as db:
        assert db.query(Customer).count() >= 3
