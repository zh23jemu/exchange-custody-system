[根目录](../../CLAUDE.md) > **app**

# app/ · 应用主体模块

---

## 模块职责

应用的全部核心代码所在目录，包含：路由层、业务逻辑层、ORM 数据模型、Jinja2 模板和 CSS 样式。

---

## 入口与启动

- 应用入口：`app/main.py`，FastAPI 实例名为 `app`
- 启动命令：`uvicorn app.main:app --reload`
- 生命周期（`lifespan`）：应用启动时自动建表（`Base.metadata.create_all`）并写入默认汇率（`seed_default_rates`）

---

## 对外接口

### HTTP 路由（全部为 HTML 表单交互）

| 路由 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 重定向到 `/orders` |
| `/dashboard` | GET | 系统概览页 |
| `/sample-data` | POST | 初始化演示数据（仅空库可用） |
| `/entities` | GET | 实体管理页面 |
| `/customers` | POST | 新建客户 |
| `/suppliers` | POST | 新建中转商 |
| `/company-accounts` | POST | 新建公司账号 |
| `/customer-target-accounts` | POST | 新建客户目标账号 |
| `/orders` | GET | 订单工作台（多维度筛选+排序） |
| `/orders/cash` | POST | 新建现金订单 |
| `/orders/bank-transfer` | POST | 新建转账订单 |
| `/orders/{id}/advance` | POST | 推进订单状态 |
| `/orders/{id}/target-account` | POST | 补录目标账号 |
| `/orders/{id}/payout` | POST | 补录转出金额和币种 |
| `/orders/{id}/notes` | POST | 更新订单备注 |
| `/exchange` | GET/POST | 货币兑换页面及执行兑换 |
| `/balances` | GET | 公司账号实时余额 |
| `/statement` | GET | 账号流水（账号/币种/日期范围筛选） |
| `/statement/export` | GET | 导出流水为 CSV（UTF-8 BOM） |
| `/customers/{id}/ledger` | GET | 客户个人账单 |
| `/settings/rates` | GET/POST | AUD 基准汇率查看与修改 |

---

## 关键依赖与配置

### 外部依赖（requirements.txt）

| 包 | 版本 | 用途 |
|---|---|---|
| fastapi | 0.116.1 | Web 框架 |
| uvicorn | 0.35.0 | ASGI 服务器 |
| jinja2 | 3.1.6 | 服务端 HTML 模板 |
| sqlalchemy | 2.0.43 | ORM + 查询构建 |
| python-multipart | 0.0.20 | 表单数据解析（FastAPI 依赖） |
| itsdangerous | 2.2.0 | Session 签名（SessionMiddleware） |
| pytest | 8.4.1 | 测试框架 |
| httpx | 0.28.1 | HTTP 客户端（测试用） |

### 关键配置

- Session 密钥：`"exchange-custody-system-secret"`（写死在 `main.py`，生产环境建议通过环境变量注入）
- 数据库 URL：默认 `sqlite:///data/app.db`，可通过 `DATABASE_URL` 环境变量覆盖
- 支持货币：`constants.py` 中 `CURRENCIES = ("AUD", "USD", "CNY", "EUR")`

---

## 数据模型

### 8 张数据库表

| 模型类 | 表名 | 主要字段 |
|---|---|---|
| `Customer` | customers | id, name, contact, created_at, updated_at |
| `Supplier` | suppliers | id, name, contact, created_at, updated_at |
| `CompanyAccount` | company_accounts | id, name, bank_name, account_no, primary_currency |
| `CustomerTargetAccount` | customer_target_accounts | id, customer_id(FK), account_name, bank_name, account_no, currency, holder_name |
| `Order` | orders | id, order_type, customer_id(FK), supplier_id(FK,可空), company_account_id(FK), target_account_id(FK,可空), deposit_amount, deposit_currency, payout_amount(可空), payout_currency(可空), status, notes |
| `OrderStatusLog` | order_status_logs | id, order_id(FK), from_status, to_status, note, created_at |
| `ExchangeRate` | exchange_rates | id, currency(唯一), rate_to_aud_base |
| `ExchangeRecord` | exchange_records | id, company_account_id(FK), source_currency, source_amount, target_currency, target_amount, exchange_rate |
| `AccountBalanceLedger` | account_balance_ledger | id, company_account_id(FK), order_id(FK,可空), customer_id(FK,可空), entry_kind, currency, amount_delta, reference_note |

### 账本分录类型（entry_kind）

| 常量 | 值 | 触发时机 |
|---|---|---|
| `LEDGER_KIND_ORDER_INFLOW` | order_inflow | 转账订单创建时 / 现金订单推进到"在公司账号"时 |
| `LEDGER_KIND_ORDER_PAYOUT` | order_payout | 订单推进到"已完成"时（负值） |
| `LEDGER_KIND_EXCHANGE_OUT` | exchange_out | 执行兑换时，扣减源币种（负值） |
| `LEDGER_KIND_EXCHANGE_IN` | exchange_in | 执行兑换时，增加目标币种（正值） |

### 订单状态机

```
现金订单: 待处理 → 交中转商 → 在公司账号 → 已完成
转账订单:               在公司账号 → 已完成
```

推进到"在公司账号"时写入 order_inflow 分录；推进到"已完成"前校验：目标账号已填、转出信息已填、账号余额充足，然后写入 order_payout 分录（负值扣减余额）。

---

## 核心业务函数

### services.py 公开接口

| 函数 | 说明 |
|---|---|
| `seed_default_rates(db)` | 初始化默认汇率（启动时调用） |
| `get_rates_map(db)` | 获取当前所有汇率字典 |
| `calculate_exchange_amount(rates, src, tgt, amt)` | 计算兑换金额和实际汇率（以 AUD 为基准中间货币） |
| `get_balance(db, account_id, currency)` | 查询单账号单币种余额（聚合 ledger） |
| `get_account_balances(db)` | 查询所有账号所有币种余额 |
| `create_customer/supplier/company_account/customer_target_account(...)` | 创建各类实体 |
| `create_order(db, ...)` | 创建订单（含校验和初始账本分录） |
| `advance_order(db, order_id)` | 推进订单状态（含余额操作） |
| `update_order_target_account/payout_details/notes(...)` | 订单字段补录 |
| `create_exchange(db, ...)` | 执行货币兑换（含余额校验和双向分录） |
| `update_exchange_rate(db, ...)` | 更新汇率 |
| `get_orders(db, ...)` | 订单列表查询（支持状态/客户/账号/目标账号/关键字/排序） |
| `get_dashboard_stats(db)` | 首页统计数字 |
| `get_customer_ledger_summary(db, customer_id)` | 客户账单（分录列表 + 按币种汇总） |
| `get_account_statement(db, ...)` | 公司账号流水（支持账号/币种/日期筛选，含汇总） |
| `create_sample_data(db)` | 初始化演示数据（仅空库） |

---

## 模板文件清单

| 文件 | 对应页面 |
|---|---|
| `templates/base.html` | 基础布局：导航栏、Flash 消息、Schema 警告横幅 |
| `templates/index.html` | `/dashboard` 系统概览 |
| `templates/orders.html` | `/orders` 订单工作台（侧边栏 + 主表格，含行内编辑） |
| `templates/entities.html` | `/entities` 实体管理（4 类实体的新增表单和列表） |
| `templates/exchange.html` | `/exchange` 货币兑换 |
| `templates/balances.html` | `/balances` 账号余额 |
| `templates/statement.html` | `/statement` 账号流水（含 CSV 导出按钮） |
| `templates/customer_ledger.html` | `/customers/{id}/ledger` 客户账单 |
| `templates/rates.html` | `/settings/rates` 汇率设置 |

---

## 测试与质量

- 测试文件：`tests/test_app.py`
- 运行：`.venv\Scripts\python.exe -m pytest tests/ -v`
- 每个测试用例使用独立的内存 SQLite，通过 FastAPI 依赖覆盖（`app.dependency_overrides`）注入测试数据库
- 当前无代码覆盖率配置，无 CI/CD 配置

---

## 常见问题 (FAQ)

**Q：订单状态推进后如何回退？**
A：当前版本不支持回退，状态只能前进。如需回退，只能直接修改数据库。

**Q：怎么添加新的支持货币？**
A：修改 `app/constants.py` 中的 `CURRENCIES` 元组和 `DEFAULT_RATE_BASE` 字典，重启应用后新汇率会自动写入数据库。

**Q：数据库文件在哪？**
A：`data/app.db`，该目录被 `.gitignore` 排除，不会提交到 Git。

**Q：Session 密钥是什么？**
A：当前写死为 `"exchange-custody-system-secret"`，生产环境建议通过环境变量 `SESSION_SECRET` 注入。

**Q：运行旧数据库时出现 Schema 警告横幅？**
A：运行 `scripts/migrate_orders_target_account_nullable.py` 迁移脚本，将 `orders` 表中相关字段改为可空。

---

## 相关文件清单

```
app/
├── __init__.py                        # 空文件，标识 Python 包
├── constants.py                       # 业务常量
├── db.py                              # 数据库配置与 Schema 迁移检测
├── models.py                          # SQLAlchemy ORM 模型（8 张表）
├── services.py                        # 全部业务逻辑（~760 行）
├── main.py                            # FastAPI 应用与路由（~590 行）
├── static/
│   └── style.css                      # 全局 CSS（暖色调，336 行）
└── templates/
    ├── base.html                      # 基础布局模板
    ├── index.html                     # 系统概览
    ├── orders.html                    # 订单工作台
    ├── entities.html                  # 实体管理
    ├── exchange.html                  # 货币兑换
    ├── balances.html                  # 账号余额
    ├── statement.html                 # 账号流水
    ├── customer_ledger.html           # 客户账单
    └── rates.html                     # 汇率设置
```

---

## 变更记录 (Changelog)

| 日期 | 内容 |
|---|---|
| 2026-04-30 | 初次生成模块文档 |
