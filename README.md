# 12-ladderbill（阶梯电费）

Ladderbill — 居民阶梯电价分段累进（含尖峰系数）

## 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://localhost:4100 |
| API | http://localhost:9100 |

## 主链

抄表录入（按账期） → 停电信用登记/作废 → 毛电量扣除有效信用得净电量 → 阶梯分段计费（含尖峰） → 账单明细

## 停电电量信用

- 按户、按账期登记停电信用电量，支持多笔累加；单笔与有效合计均不得超过该账期抄表毛电量，超额拒绝（409），错误体含可读原因与 `excess_kwh` 超限差额。
- 信用可作废：作废后不再参与计费扣除，但审计行（作废时间、原因）永久保留，重复作废返回 409。
- 计费口径：`净电量 = 毛电量 − 有效信用合计`，再对净电量做阶梯分段与尖峰；回包包含 `gross_kwh / credit_kwh / net_kwh`、参与扣除的信用行与分段明细。
- `POST /api/bill` 传 `persist=false` 为试算，只预览扣除与分段，不写 `calc_runs`。
- 主要接口：`GET/POST /api/accounts/{id}/credits`、`GET /api/accounts/{id}/credits/summary?period=`、`POST /api/credits/{id}/void`。
- 前端：户详情页维护信用明细与作废；测算台选户选账期展示毛/扣除/净，作废后再次试算净电量回升，作废记录仍可查阅。

## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。
