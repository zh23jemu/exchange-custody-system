# 换汇资金托管系统

基于 `FastAPI + Jinja2 + SQLite + SQLAlchemy` 的轻量级换汇资金托管 Web 系统。

## 功能

- 客户、中转商、公司账号、客户目标账号管理
- 现金订单与直接转账订单创建
- 订单状态流转与资金台账记录
- 公司账号多币种余额查看
- 公司账号内货币兑换
- 客户流水与汇总报表
- AUD 基准汇率维护

## 运行

Windows:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run_server.py
```

启动后访问：

[http://127.0.0.1:8080](http://127.0.0.1:8080)

## 服务器部署

默认监听：

- `HOST=0.0.0.0`
- `PORT=8080`

如果要切换端口：

```powershell
$env:PORT="9000"
.venv\Scripts\python.exe run_server.py
```

如果要开启热更新：

```powershell
$env:RELOAD="true"
.venv\Scripts\python.exe run_server.py
```

## 数据库迁移

如果你之前已经运行过旧版本，旧的 `data/app.db` 里以下字段可能还是必填：

- `orders.target_account_id`
- `orders.payout_amount`
- `orders.payout_currency`

这会导致“创建订单时只录入入金信息”无法真正写入数据库。

迁移命令：

```powershell
.venv\Scripts\python.exe scripts\migrate_orders_target_account_nullable.py
```

迁移完成后再启动程序即可。
