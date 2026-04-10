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
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

启动后访问：

[http://127.0.0.1:8000](http://127.0.0.1:8000)
