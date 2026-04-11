from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from .constants import (
    BANK_ORDER_FLOW,
    CASH_ORDER_FLOW,
    CURRENCIES,
    DEFAULT_RATE_BASE,
    LEDGER_KIND_EXCHANGE_IN,
    LEDGER_KIND_EXCHANGE_OUT,
    LEDGER_KIND_ORDER_INFLOW,
    LEDGER_KIND_ORDER_PAYOUT,
    ORDER_STATUS_COMPLETED,
    ORDER_STATUS_IN_COMPANY,
    ORDER_TYPE_BANK,
    ORDER_TYPE_CASH,
)
from .models import (
    AccountBalanceLedger,
    CompanyAccount,
    Customer,
    CustomerTargetAccount,
    ExchangeRate,
    ExchangeRecord,
    Order,
    OrderStatusLog,
    Supplier,
)


TWOPLACES = Decimal("0.01")
SIXPLACES = Decimal("0.000001")


class BusinessError(Exception):
    pass


def quantize_money(value: Decimal | str | float) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def quantize_rate(value: Decimal | str | float) -> Decimal:
    return Decimal(str(value)).quantize(SIXPLACES, rounding=ROUND_HALF_UP)


def seed_default_rates(db: Session) -> None:
    existing = {row.currency for row in db.scalars(select(ExchangeRate)).all()}
    for currency, rate in DEFAULT_RATE_BASE.items():
        if currency not in existing:
            db.add(ExchangeRate(currency=currency, rate_to_aud_base=quantize_rate(rate)))
    db.commit()


def get_rates_map(db: Session) -> dict[str, Decimal]:
    rows = db.scalars(select(ExchangeRate)).all()
    data = {row.currency: Decimal(row.rate_to_aud_base) for row in rows}
    if "AUD" not in data:
        data["AUD"] = Decimal("1")
    return data


def calculate_exchange_amount(
    rates: dict[str, Decimal], source_currency: str, target_currency: str, source_amount: Decimal
) -> tuple[Decimal, Decimal]:
    source_amount = quantize_money(source_amount)
    if source_currency == target_currency:
        return source_amount, Decimal("1")
    if source_currency == "AUD":
        rate = rates[target_currency]
        return quantize_money(source_amount * rate), quantize_rate(rate)
    if target_currency == "AUD":
        rate = Decimal("1") / rates[source_currency]
        return quantize_money(source_amount * rate), quantize_rate(rate)
    aud_amount = source_amount / rates[source_currency]
    target_amount = aud_amount * rates[target_currency]
    return quantize_money(target_amount), quantize_rate(target_amount / source_amount)


def get_balance(db: Session, account_id: int, currency: str) -> Decimal:
    amount = db.scalar(
        select(func.coalesce(func.sum(AccountBalanceLedger.amount_delta), 0)).where(
            AccountBalanceLedger.company_account_id == account_id,
            AccountBalanceLedger.currency == currency,
        )
    )
    return quantize_money(amount or 0)


def get_account_balances(db: Session) -> dict[int, dict[str, Decimal]]:
    rows = db.execute(
        select(
            AccountBalanceLedger.company_account_id,
            AccountBalanceLedger.currency,
            func.coalesce(func.sum(AccountBalanceLedger.amount_delta), 0),
        ).group_by(AccountBalanceLedger.company_account_id, AccountBalanceLedger.currency)
    ).all()
    data: dict[int, dict[str, Decimal]] = defaultdict(dict)
    for account_id, currency, total in rows:
        data[account_id][currency] = quantize_money(total)
    return data


def validate_currency(currency: str) -> None:
    if currency not in CURRENCIES:
        raise BusinessError(f"不支持的币种：{currency}")


def create_customer(db: Session, name: str, contact: str) -> Customer:
    customer = Customer(name=name.strip(), contact=contact.strip())
    db.add(customer)
    db.commit()
    return customer


def create_supplier(db: Session, name: str, contact: str) -> Supplier:
    supplier = Supplier(name=name.strip(), contact=contact.strip())
    db.add(supplier)
    db.commit()
    return supplier


def create_company_account(
    db: Session, name: str, bank_name: str, account_no: str, primary_currency: str
) -> CompanyAccount:
    validate_currency(primary_currency)
    account = CompanyAccount(
        name=name.strip(),
        bank_name=bank_name.strip(),
        account_no=account_no.strip(),
        primary_currency=primary_currency,
    )
    db.add(account)
    db.commit()
    return account


def create_customer_target_account(
    db: Session,
    customer_id: int,
    account_name: str,
    bank_name: str,
    account_no: str,
    currency: str,
    holder_name: str,
) -> CustomerTargetAccount:
    validate_currency(currency)
    account = CustomerTargetAccount(
        customer_id=customer_id,
        account_name=account_name.strip(),
        bank_name=bank_name.strip(),
        account_no=account_no.strip(),
        currency=currency,
        holder_name=holder_name.strip(),
    )
    db.add(account)
    db.commit()
    return account


def log_status(db: Session, order: Order, to_status: str, from_status: str | None = None, note: str = ""):
    db.add(OrderStatusLog(order_id=order.id, from_status=from_status, to_status=to_status, note=note))


def add_ledger_entry(
    db: Session,
    account_id: int,
    currency: str,
    amount_delta: Decimal,
    entry_kind: str,
    note: str,
    order_id: int | None = None,
    customer_id: int | None = None,
) -> None:
    db.add(
        AccountBalanceLedger(
            company_account_id=account_id,
            currency=currency,
            amount_delta=quantize_money(amount_delta),
            entry_kind=entry_kind,
            reference_note=note,
            order_id=order_id,
            customer_id=customer_id,
        )
    )


def _validate_order_relations(db: Session, customer_id: int, target_account_id: int, supplier_id: int | None) -> None:
    customer = db.get(Customer, customer_id)
    target = db.get(CustomerTargetAccount, target_account_id)
    if customer is None or target is None:
        raise BusinessError("客户或目标账号不存在")
    if target.customer_id != customer_id:
        raise BusinessError("客户目标账号不属于当前客户")
    if supplier_id is not None and db.get(Supplier, supplier_id) is None:
        raise BusinessError("中转商不存在")


def create_order(
    db: Session,
    order_type: str,
    customer_id: int,
    company_account_id: int,
    target_account_id: int,
    deposit_amount: Decimal,
    deposit_currency: str,
    payout_amount: Decimal,
    payout_currency: str,
    supplier_id: int | None = None,
    notes: str = "",
) -> Order:
    validate_currency(deposit_currency)
    validate_currency(payout_currency)
    _validate_order_relations(db, customer_id, target_account_id, supplier_id)
    if db.get(CompanyAccount, company_account_id) is None:
        raise BusinessError("公司账号不存在")
    deposit_amount = quantize_money(deposit_amount)
    payout_amount = quantize_money(payout_amount)
    if deposit_amount <= 0 or payout_amount <= 0:
        raise BusinessError("金额必须大于 0")

    if order_type == ORDER_TYPE_CASH:
        status = CASH_ORDER_FLOW[0]
    elif order_type == ORDER_TYPE_BANK:
        status = BANK_ORDER_FLOW[0]
    else:
        raise BusinessError("无效的订单类型")

    order = Order(
        order_type=order_type,
        customer_id=customer_id,
        supplier_id=supplier_id,
        company_account_id=company_account_id,
        target_account_id=target_account_id,
        deposit_amount=deposit_amount,
        deposit_currency=deposit_currency,
        payout_amount=payout_amount,
        payout_currency=payout_currency,
        status=status,
        notes=notes.strip(),
    )
    db.add(order)
    db.flush()
    log_status(db, order, to_status=status, note="订单创建")
    if order_type == ORDER_TYPE_BANK:
        add_ledger_entry(
            db,
            account_id=company_account_id,
            currency=deposit_currency,
            amount_delta=deposit_amount,
            entry_kind=LEDGER_KIND_ORDER_INFLOW,
            note=f"订单 #{order.id} 入账",
            order_id=order.id,
            customer_id=customer_id,
        )
    db.commit()
    db.refresh(order)
    return order


def next_status_for(order: Order) -> str | None:
    flow = CASH_ORDER_FLOW if order.order_type == ORDER_TYPE_CASH else BANK_ORDER_FLOW
    if order.status not in flow:
        raise BusinessError("订单状态异常")
    index = flow.index(order.status)
    if index >= len(flow) - 1:
        return None
    return flow[index + 1]


def advance_order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise BusinessError("订单不存在")
    next_status = next_status_for(order)
    if next_status is None:
        raise BusinessError("订单已是最终状态，不能继续推进")
    if next_status == ORDER_STATUS_IN_COMPANY:
        add_ledger_entry(
            db,
            account_id=order.company_account_id,
            currency=order.deposit_currency,
            amount_delta=order.deposit_amount,
            entry_kind=LEDGER_KIND_ORDER_INFLOW,
            note=f"订单 #{order.id} 入账",
            order_id=order.id,
            customer_id=order.customer_id,
        )
    if next_status == ORDER_STATUS_COMPLETED:
        current_balance = get_balance(db, order.company_account_id, order.payout_currency)
        if current_balance < order.payout_amount:
            raise BusinessError(
                f"账号余额不足，当前 {order.payout_currency} 余额为 {current_balance}，无法完成转出"
            )
        add_ledger_entry(
            db,
            account_id=order.company_account_id,
            currency=order.payout_currency,
            amount_delta=-order.payout_amount,
            entry_kind=LEDGER_KIND_ORDER_PAYOUT,
            note=f"订单 #{order.id} 对外转账",
            order_id=order.id,
            customer_id=order.customer_id,
        )
    old_status = order.status
    order.status = next_status
    log_status(db, order, to_status=next_status, from_status=old_status, note="推进订单状态")
    db.commit()
    db.refresh(order)
    return order


def create_exchange(
    db: Session,
    company_account_id: int,
    source_currency: str,
    source_amount: Decimal,
    target_currency: str,
) -> ExchangeRecord:
    validate_currency(source_currency)
    validate_currency(target_currency)
    if source_currency == target_currency:
        raise BusinessError("源币种和目标币种不能相同")
    if db.get(CompanyAccount, company_account_id) is None:
        raise BusinessError("公司账号不存在")
    source_amount = quantize_money(source_amount)
    if source_amount <= 0:
        raise BusinessError("兑换金额必须大于 0")
    current_balance = get_balance(db, company_account_id, source_currency)
    if current_balance < source_amount:
        raise BusinessError(
            f"余额不足，当前 {source_currency} 余额为 {current_balance}，无法发起兑换"
        )
    rates = get_rates_map(db)
    target_amount, effective_rate = calculate_exchange_amount(
        rates, source_currency, target_currency, source_amount
    )
    record = ExchangeRecord(
        company_account_id=company_account_id,
        source_currency=source_currency,
        source_amount=source_amount,
        target_currency=target_currency,
        target_amount=target_amount,
        exchange_rate=effective_rate,
    )
    db.add(record)
    db.flush()
    add_ledger_entry(
        db,
        account_id=company_account_id,
        currency=source_currency,
        amount_delta=-source_amount,
        entry_kind=LEDGER_KIND_EXCHANGE_OUT,
        note=f"兑换记录 #{record.id} 扣减",
    )
    add_ledger_entry(
        db,
        account_id=company_account_id,
        currency=target_currency,
        amount_delta=target_amount,
        entry_kind=LEDGER_KIND_EXCHANGE_IN,
        note=f"兑换记录 #{record.id} 增加",
    )
    db.commit()
    db.refresh(record)
    return record


def update_exchange_rate(db: Session, currency: str, rate_to_aud_base: Decimal) -> ExchangeRate:
    validate_currency(currency)
    if currency == "AUD":
        rate_to_aud_base = Decimal("1")
    rate_to_aud_base = quantize_rate(rate_to_aud_base)
    if rate_to_aud_base <= 0:
        raise BusinessError("汇率必须大于 0")
    row = db.scalar(select(ExchangeRate).where(ExchangeRate.currency == currency))
    if row is None:
        row = ExchangeRate(currency=currency, rate_to_aud_base=rate_to_aud_base)
        db.add(row)
    else:
        row.rate_to_aud_base = rate_to_aud_base
    db.commit()
    return row


def get_orders(db: Session, status: str | None = None) -> list[Order]:
    stmt = (
        select(Order)
        .options(
            joinedload(Order.customer),
            joinedload(Order.supplier),
            joinedload(Order.company_account),
            joinedload(Order.target_account),
        )
        .order_by(Order.created_at.desc())
    )
    if status:
        stmt = stmt.where(Order.status == status)
    return list(db.scalars(stmt).unique().all())


def get_dashboard_stats(db: Session) -> dict[str, int]:
    return {
        "customers": db.scalar(select(func.count(Customer.id))) or 0,
        "suppliers": db.scalar(select(func.count(Supplier.id))) or 0,
        "accounts": db.scalar(select(func.count(CompanyAccount.id))) or 0,
        "pending_orders": db.scalar(
            select(func.count(Order.id)).where(Order.status != ORDER_STATUS_COMPLETED)
        )
        or 0,
    }


def get_customer_ledger_summary(db: Session, customer_id: int) -> tuple[list[AccountBalanceLedger], dict[str, Decimal]]:
    stmt = (
        select(AccountBalanceLedger)
        .where(AccountBalanceLedger.customer_id == customer_id)
        .order_by(AccountBalanceLedger.created_at.desc())
    )
    entries = list(db.scalars(stmt).all())
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for entry in entries:
        totals[entry.currency] += Decimal(entry.amount_delta)
    return entries, {currency: quantize_money(total) for currency, total in totals.items()}


def create_sample_data(db: Session) -> None:
    has_data = db.scalar(select(func.count(Customer.id))) or 0
    if has_data:
        raise BusinessError("系统中已经存在数据，示例数据只允许在空库中初始化")

    alice = create_customer(db, "Alice", "微信: alice-fx")
    chen = create_customer(db, "陈先生", "微信: chen-cny")
    emma = create_customer(db, "Emma", "电话: 0400-000-001")

    bob = create_supplier(db, "Bob", "微信: bob-bridge")
    pin = create_supplier(db, "PIN", "微信: pin-bridge")

    hsbc_aud = create_company_account(db, "HSBC AUD 主账号", "HSBC", "AU-001-8899", "AUD")
    cba_usd = create_company_account(db, "CBA USD 备用账号", "Commonwealth", "US-7788-1122", "USD")

    alice_target = create_customer_target_account(
        db, alice.id, "Alice 美元收款卡", "Bank of America", "US-ACC-1001", "USD", "Alice"
    )
    chen_target = create_customer_target_account(
        db, chen.id, "陈先生 人民币卡", "中国银行", "CN-ACC-2001", "CNY", "陈先生"
    )
    emma_target = create_customer_target_account(
        db, emma.id, "Emma 欧元账号", "Deutsche Bank", "EU-ACC-3001", "EUR", "Emma"
    )

    order1 = create_order(
        db,
        order_type=ORDER_TYPE_BANK,
        customer_id=alice.id,
        company_account_id=hsbc_aud.id,
        target_account_id=alice_target.id,
        deposit_amount=Decimal("1200"),
        deposit_currency="AUD",
        payout_amount=Decimal("620"),
        payout_currency="USD",
        notes="客户直接入账，后续换汇到美元",
    )
    create_exchange(db, hsbc_aud.id, "AUD", Decimal("1000"), "USD")
    advance_order(db, order1.id)

    order2 = create_order(
        db,
        order_type=ORDER_TYPE_CASH,
        customer_id=chen.id,
        supplier_id=bob.id,
        company_account_id=hsbc_aud.id,
        target_account_id=chen_target.id,
        deposit_amount=Decimal("3000"),
        deposit_currency="AUD",
        payout_amount=Decimal("14100"),
        payout_currency="CNY",
        notes="现金单，已交中转商并确认到账，待后续完成",
    )
    advance_order(db, order2.id)
    advance_order(db, order2.id)

    order3 = create_order(
        db,
        order_type=ORDER_TYPE_CASH,
        customer_id=emma.id,
        supplier_id=pin.id,
        company_account_id=cba_usd.id,
        target_account_id=emma_target.id,
        deposit_amount=Decimal("2000"),
        deposit_currency="USD",
        payout_amount=Decimal("1800"),
        payout_currency="EUR",
        notes="新建现金单，尚未交给中转商",
    )

    order4 = create_order(
        db,
        order_type=ORDER_TYPE_BANK,
        customer_id=chen.id,
        company_account_id=cba_usd.id,
        target_account_id=chen_target.id,
        deposit_amount=Decimal("2500"),
        deposit_currency="USD",
        payout_amount=Decimal("2200"),
        payout_currency="USD",
        notes="直接转账单，已在公司账号待完成",
    )

    create_exchange(db, cba_usd.id, "USD", Decimal("300"), "EUR")

    if order3.id <= 0 or order4.id <= 0:
        raise BusinessError("示例数据初始化失败")
