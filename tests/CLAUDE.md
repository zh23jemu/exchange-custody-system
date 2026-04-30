[根目录](../CLAUDE.md) > **tests**

# tests/ · 集成测试模块

---

## 模块职责

使用 pytest + FastAPI TestClient 对整个应用进行集成测试，每个测试用例使用独立的内存 SQLite 数据库，互不干扰。

---

## 入口与启动

- 测试文件：`tests/test_app.py`
- 运行命令：`.venv\Scripts\python.exe -m pytest tests/ -v`

---

## 测试覆盖场景

| 测试函数 | 覆盖内容 |
|---|---|
| `test_entities_and_cash_order_flow` | 创建客户/中转商/公司账号/目标账号，完整现金订单流程（4 个状态），换汇后余额正确扣减 |
| `test_bank_order_and_rate_update` | 转账订单完整流程（2 个状态），完成后余额正确，汇率更新持久化 |
| `test_order_can_be_created_without_target_account_and_completed_after_update` | 订单创建时留空目标账号和转出信息，状态推进到"在公司账号"后被阻断，补录信息后成功完成 |
| `test_sample_data_seed_route` | 示例数据初始化创建足量实体，重复调用不会出错 |
| `test_orders_filter_accepts_empty_query_values` | 订单筛选接口兼容空字符串参数 |
| `test_account_statement_page` | 账号流水页面正常渲染 |
| `test_account_statement_export_csv` | CSV 导出接口返回正确 Content-Type 和字段头 |

---

## 关键依赖

- `pytest`（fixture 机制）
- `fastapi.testclient.TestClient`
- `sqlalchemy.pool.StaticPool`（内存数据库共享连接）

---

## 相关文件清单

```
tests/
└── test_app.py    # 全部集成测试（~300 行）
```

---

## 变更记录 (Changelog)

| 日期 | 内容 |
|---|---|
| 2026-04-30 | 初次生成模块文档 |
