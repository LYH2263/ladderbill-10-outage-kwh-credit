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

抄表录入 → 阶梯分段计费 → 账单明细

## 停电电量信用

按户按账期（YYYY-MM）登记信用电量，可多笔累加；单笔与有效合计均不得超过账期毛电量，
超额返回 422 与超限差额。计费先从毛电量扣除有效信用合计得净电量，再做阶梯分段与尖峰。
作废仅置标记、保留审计行，作废后不再参与扣除（再次测算净电量回升）。

- `GET/POST /api/accounts/{id}/credits?period=YYYY-MM`
- `POST /api/credits/{id}/void`
- `POST /api/bill` 携带 `account_id` + `period` 时自动扣除（`persist:false` 仅试算）


## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。
