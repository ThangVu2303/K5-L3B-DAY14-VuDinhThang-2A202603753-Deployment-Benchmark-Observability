# Deployment Information

## Public URL

https://agent-production-8b9dae17.up.railway.app

## Platform

**Railway**: project `day14-agent`, environment `production`, gồm 2 service:

| Service | Nguồn | Vai trò |
| --- | --- | --- |
| `agent` | `railway up` từ `06-lab-complete/`, build bằng `Dockerfile` (theo `railway.toml`) | Agent Part 6 (FastAPI, uvicorn 2 worker) |
| `Redis` | Railway Redis database | Rate limit + cost guard, nối qua private network `redis.railway.internal:6379` |

Deploy (chạy trong `06-lab-complete/`):

```bash
railway init --name day14-agent
railway add --database redis
railway add --service agent --variables 'REDIS_URL=${{Redis.REDIS_URL}}' --variables ENVIRONMENT=production ...
echo "<key>" | railway variable set AGENT_API_KEY --stdin --service agent   # key không nằm trong lệnh hay trong repo
railway up --service agent --ci
railway domain --service agent
```

## Test Commands

Đặt `BASE` là URL public và `AGENT_API_KEY` là key đã đặt trên Railway. Mỗi lệnh chỉ in mã HTTP nên chụp màn hình không lộ key.

```bash
BASE=https://agent-production-8b9dae17.up.railway.app
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Hoặc chạy cả 4 bằng script: `BASE=... AGENT_API_KEY=... bash 06-lab-complete/smoke_test.sh`

Kết quả ngày 2026-11-26:

```text
BASE=https://agent-production-8b9dae17.up.railway.app
GET /health            200 (expected 200) OK
GET /ready             200 (expected 200) OK
POST /ask (no key)     401 (expected 401) OK
POST /ask (with key)   200 (expected 200) OK
```

### Health Check

```bash
curl https://agent-production-8b9dae17.up.railway.app/health
# {"status":"ok","version":"1.0.0","environment":"production","uptime_seconds":25.0,"timestamp":"2026-11-26T08:39:51.693425+00:00"}

curl https://agent-production-8b9dae17.up.railway.app/ready
# {"ready":true,"redis":"ok"}
```

### API Test (with authentication)

```bash
curl -X POST https://agent-production-8b9dae17.up.railway.app/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "What is deployment?"}'
# {"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được.","usage":{"input_tokens":4,"output_tokens":19,"cost_usd":1.2e-05,"rate_limit_remaining":8}}
```

### Rate limit trên cloud (`RATE_LIMIT_PER_MINUTE=10`, 2 lượt đã dùng ở trên)

```text
200 200 200 200 200 200 200 200 429 429
HTTP/1.1 429 Too Many Requests
retry-after: 43
```

### Script chấm với URL public

```text
$ python check_production_ready.py --public-url https://agent-production-8b9dae17.up.railway.app
     ✅ Public URL: GET https://agent-production-8b9dae17.up.railway.app/health → 200
```

## Environment Variables Set

Đặt trên service `agent` của Railway bằng CLI, không có trong code hay trong git:

| Biến | Giá trị | Ghi chú |
| --- | --- | --- |
| `AGENT_API_KEY` | *(secret, 32 byte ngẫu nhiên)* | Đặt qua `railway variable set --stdin` |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | Biến tham chiếu, Railway tự điền URL nội bộ của service Redis |
| `ENVIRONMENT` | `production` | Ẩn `/docs`, bắt buộc phải có `AGENT_API_KEY` |
| `RATE_LIMIT_PER_MINUTE` | `10` | |
| `DAILY_BUDGET_USD` | `1.0` | |
| `LOG_LEVEL` | `INFO` | |
| `APP_VERSION` | `1.0.0` | |
| `PORT` | *(Railway tự cấp: 8080)* | Không tự đặt. Dockerfile đọc `${PORT:-8000}`, log startup ghi `port=8080` |

Log startup trên Railway (log JSON được Railway hiển thị thành field):

```text
[INFO] ts="2026-11-26T08:39:26.659+00:00" logger="agent" event="startup" version="1.0.0" environment="production" port=8080 rate_limit_per_minute=10 daily_budget_usd=1 monthly_budget_usd=null api_key_configured=true redis_ok=true
```

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
