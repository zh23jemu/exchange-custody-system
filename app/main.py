from __future__ import annotations

from decimal import Decimal
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .constants import CURRENCIES, DEFAULT_RATE_BASE, ORDER_TYPE_BANK, ORDER_TYPE_CASH
from .db import engine, get_db
from .models import Base, CompanyAccount, Customer, CustomerTargetAccount, ExchangeRate, ExchangeRecord, Supplier
from .services import (
    BusinessError,
    advance_order,
    create_company_account,
    create_customer,
    create_sample_data,
    create_customer_target_account,
    create_exchange,
    create_order,
    create_supplier,
    get_account_balances,
    get_customer_ledger_summary,
    get_dashboard_stats,
    get_orders,
    get_rates_map,
    seed_default_rates,
    update_exchange_rate,
)


BASE_PATH = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_PATH / "templates"))


def flash(request: Request, message: str, level: str = "success") -> None:
    items = request.session.get("_flash", [])
    items.append({"message": message, "level": level})
    request.session["_flash"] = items


def consume_flash(request: Request):
    items = request.session.get("_flash", [])
    request.session["_flash"] = []
    return items


def render(request: Request, template_name: str, context: dict):
    base_context = {"request": request, "messages": consume_flash(request), "currencies": CURRENCIES}
    base_context.update(context)
    return templates.TemplateResponse(request, template_name, base_context)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        seed_default_rates(db)
    finally:
        db.close()
    yield


app = FastAPI(title="换汇资金托管系统", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key="exchange-custody-system-secret")
app.mount("/static", StaticFiles(directory=str(BASE_PATH / "static")), name="static")


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    return render(
        request,
        "index.html",
        {
            "stats": get_dashboard_stats(db),
            "recent_orders": get_orders(db)[:8],
            "balances": get_account_balances(db),
            "accounts": db.scalars(select(CompanyAccount).order_by(CompanyAccount.name)).all(),
            "has_any_data": (db.scalar(select(Customer.id).limit(1)) is not None),
        },
    )


@app.post("/sample-data")
def create_sample_data_route(request: Request, db: Session = Depends(get_db)):
    try:
        create_sample_data(db)
        flash(request, "示例数据已初始化，可以直接开始体验订单、兑换和流水功能")
    except BusinessError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/", status_code=303)


@app.get("/entities")
def entities_page(request: Request, db: Session = Depends(get_db)):
    return render(
        request,
        "entities.html",
        {
            "customers": db.scalars(select(Customer).order_by(Customer.created_at.desc())).all(),
            "suppliers": db.scalars(select(Supplier).order_by(Supplier.created_at.desc())).all(),
            "company_accounts": db.scalars(select(CompanyAccount).order_by(CompanyAccount.created_at.desc())).all(),
            "target_accounts": db.scalars(select(CustomerTargetAccount).order_by(CustomerTargetAccount.created_at.desc())).all(),
        },
    )


@app.post("/customers")
def create_customer_route(request: Request, name: str = Form(...), contact: str = Form(""), db: Session = Depends(get_db)):
    try:
        create_customer(db, name=name, contact=contact)
        flash(request, "客户已创建")
    except BusinessError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/entities", status_code=303)


@app.post("/suppliers")
def create_supplier_route(request: Request, name: str = Form(...), contact: str = Form(""), db: Session = Depends(get_db)):
    try:
        create_supplier(db, name=name, contact=contact)
        flash(request, "中转商已创建")
    except BusinessError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/entities", status_code=303)


@app.post("/company-accounts")
def create_company_account_route(
    request: Request,
    name: str = Form(...),
    bank_name: str = Form(...),
    account_no: str = Form(...),
    primary_currency: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        create_company_account(db, name=name, bank_name=bank_name, account_no=account_no, primary_currency=primary_currency)
        flash(request, "公司账号已创建")
    except BusinessError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/entities", status_code=303)


@app.post("/customer-target-accounts")
def create_customer_target_account_route(
    request: Request,
    customer_id: int = Form(...),
    account_name: str = Form(...),
    bank_name: str = Form(...),
    account_no: str = Form(...),
    currency: str = Form(...),
    holder_name: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        create_customer_target_account(
            db,
            customer_id=customer_id,
            account_name=account_name,
            bank_name=bank_name,
            account_no=account_no,
            currency=currency,
            holder_name=holder_name,
        )
        flash(request, "客户目标账号已创建")
    except BusinessError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/entities", status_code=303)


@app.get("/orders")
def orders_page(request: Request, status: str | None = None, db: Session = Depends(get_db)):
    return render(
        request,
        "orders.html",
        {
            "customers": db.scalars(select(Customer).order_by(Customer.name)).all(),
            "suppliers": db.scalars(select(Supplier).order_by(Supplier.name)).all(),
            "company_accounts": db.scalars(select(CompanyAccount).order_by(CompanyAccount.name)).all(),
            "target_accounts": db.scalars(select(CustomerTargetAccount).order_by(CustomerTargetAccount.created_at.desc())).all(),
            "orders": get_orders(db, status=status),
            "selected_status": status or "",
            "all_statuses": ["待处理", "交中转商", "在公司账号", "已完成"],
        },
    )


def _create_order_redirect(request: Request, db: Session, **payload):
    try:
        create_order(db, **payload)
        flash(request, f"{payload['order_type']}已创建")
    except (BusinessError, ArithmeticError, ValueError) as exc:
        flash(request, f"创建订单失败：{exc}", "error")
    return RedirectResponse("/orders", status_code=303)


@app.post("/orders/cash")
def create_cash_order_route(
    request: Request,
    customer_id: int = Form(...),
    supplier_id: int = Form(...),
    company_account_id: int = Form(...),
    target_account_id: int = Form(...),
    deposit_amount: str = Form(...),
    deposit_currency: str = Form(...),
    payout_amount: str = Form(...),
    payout_currency: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    return _create_order_redirect(
        request,
        db,
        order_type=ORDER_TYPE_CASH,
        customer_id=customer_id,
        company_account_id=company_account_id,
        target_account_id=target_account_id,
        deposit_amount=Decimal(deposit_amount),
        deposit_currency=deposit_currency,
        payout_amount=Decimal(payout_amount),
        payout_currency=payout_currency,
        supplier_id=supplier_id,
        notes=notes,
    )


@app.post("/orders/bank-transfer")
def create_bank_order_route(
    request: Request,
    customer_id: int = Form(...),
    company_account_id: int = Form(...),
    target_account_id: int = Form(...),
    deposit_amount: str = Form(...),
    deposit_currency: str = Form(...),
    payout_amount: str = Form(...),
    payout_currency: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    return _create_order_redirect(
        request,
        db,
        order_type=ORDER_TYPE_BANK,
        customer_id=customer_id,
        company_account_id=company_account_id,
        target_account_id=target_account_id,
        deposit_amount=Decimal(deposit_amount),
        deposit_currency=deposit_currency,
        payout_amount=Decimal(payout_amount),
        payout_currency=payout_currency,
        supplier_id=None,
        notes=notes,
    )


@app.post("/orders/{order_id}/advance")
def advance_order_route(request: Request, order_id: int, db: Session = Depends(get_db)):
    try:
        order = advance_order(db, order_id)
        flash(request, f"订单 #{order.id} 已推进到 {order.status}")
    except BusinessError as exc:
        flash(request, str(exc), "error")
    return RedirectResponse("/orders", status_code=303)


@app.get("/exchange")
def exchange_page(request: Request, db: Session = Depends(get_db)):
    return render(
        request,
        "exchange.html",
        {
            "company_accounts": db.scalars(select(CompanyAccount).order_by(CompanyAccount.name)).all(),
            "records": db.scalars(select(ExchangeRecord).order_by(ExchangeRecord.created_at.desc())).all(),
            "balances": get_account_balances(db),
            "rates": get_rates_map(db),
        },
    )


@app.post("/exchange")
def create_exchange_route(
    request: Request,
    company_account_id: int = Form(...),
    source_currency: str = Form(...),
    source_amount: str = Form(...),
    target_currency: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        create_exchange(
            db,
            company_account_id=company_account_id,
            source_currency=source_currency,
            source_amount=Decimal(source_amount),
            target_currency=target_currency,
        )
        flash(request, "兑换已执行")
    except (BusinessError, ArithmeticError, ValueError) as exc:
        flash(request, f"兑换失败：{exc}", "error")
    return RedirectResponse("/exchange", status_code=303)


@app.get("/balances")
def balances_page(request: Request, db: Session = Depends(get_db)):
    return render(
        request,
        "balances.html",
        {
            "company_accounts": db.scalars(select(CompanyAccount).order_by(CompanyAccount.name)).all(),
            "balances": get_account_balances(db),
        },
    )


@app.get("/customers/{customer_id}/ledger")
def customer_ledger_page(request: Request, customer_id: int, db: Session = Depends(get_db)):
    selected_customer = db.get(Customer, customer_id)
    if selected_customer is None:
        flash(request, "客户不存在", "error")
        return RedirectResponse("/entities", status_code=303)
    entries, summary = get_customer_ledger_summary(db, customer_id)
    return render(
        request,
        "customer_ledger.html",
        {
            "customers": db.scalars(select(Customer).order_by(Customer.name)).all(),
            "selected_customer": selected_customer,
            "entries": entries,
            "summary": summary,
            "target_accounts": db.scalars(select(CustomerTargetAccount).where(CustomerTargetAccount.customer_id == customer_id)).all(),
        },
    )


@app.get("/settings/rates")
def rates_page(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(ExchangeRate).order_by(ExchangeRate.currency)).all()
    existing = {row.currency: row for row in rows}
    ordered = []
    for currency in CURRENCIES:
        ordered.append(existing.get(currency) or ExchangeRate(currency=currency, rate_to_aud_base=DEFAULT_RATE_BASE[currency]))
    return render(request, "rates.html", {"rates": ordered})


@app.post("/settings/rates")
def update_rate_route(
    request: Request,
    currency: str = Form(...),
    rate_to_aud_base: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        update_exchange_rate(db, currency=currency, rate_to_aud_base=Decimal(rate_to_aud_base))
        flash(request, f"{currency} 汇率已更新")
    except (BusinessError, ArithmeticError, ValueError) as exc:
        flash(request, f"汇率更新失败：{exc}", "error")
    return RedirectResponse("/settings/rates", status_code=303)
