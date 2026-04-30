[根目录](../CLAUDE.md) > **scripts**

# scripts/ · 数据库迁移工具

---

## 模块职责

存放一次性数据库迁移脚本，用于处理 SQLite 不支持 ALTER COLUMN 的限制（需通过建新表、复制数据、删旧表、重命名的方式完成字段约束变更）。

---

## 脚本清单

### `migrate_orders_target_account_nullable.py`

**背景**：早期版本中 `orders` 表的 `target_account_id`、`payout_amount`、`payout_currency` 三个字段为必填（NOT NULL），后续需求要求允许创建订单时留空，后续补录。

**功能**：
1. 检测当前数据库中这三个字段是否仍为 NOT NULL
2. 如已是新结构则直接退出（幂等）
3. 创建新的 `orders_new` 表（三字段改为可空）
4. 复制全部数据
5. 删除旧表并重命名
6. 重建索引（customer_id、company_account_id、target_account_id）

**运行方式**：

```bash
.venv\Scripts\python.exe scripts/migrate_orders_target_account_nullable.py
```

**注意**：运行前需确保 `data/app.db` 存在；操作使用事务，失败会自动回滚。

---

## 相关文件清单

```
scripts/
└── migrate_orders_target_account_nullable.py
```

---

## 变更记录 (Changelog)

| 日期 | 内容 |
|---|---|
| 2026-04-30 | 初次生成模块文档 |
