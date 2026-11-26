# Mission Answers — Day 14

## Part 1 — Localhost vs Production

### Exercise 1.1 — Anti-patterns trong `develop/app.py`

| # | Anti-pattern | Dòng code | Hậu quả |
| --- | --- | --- | --- |
| 1 | Hardcode secret | `OPENAI_API_KEY = "sk-hardcoded-..."` (dòng 17), `DATABASE_URL = "postgresql://admin:password123@..."` (dòng 18) | Push lên GitHub là lộ key và mật khẩu DB. Xoá file cũng không đủ vì secret vẫn nằm trong lịch sử git |
| 2 | Log ra secret | `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` (dòng 34) | Ai đọc được log (log aggregator, đồng nghiệp, nhà cung cấp cloud) đều thấy key |
| 3 | Dùng `print()` thay vì logging | dòng 33, 34, 38 | Không có level, không có timestamp, không parse được. Trên Windows còn làm `/ask` trả **500** (xem 1.2) |
| 4 | Config cứng trong code | `DEBUG = True`, `MAX_TOKENS = 500` (dòng 21–22) | Muốn đổi giữa dev/staging/prod thì phải sửa code và build lại |
| 5 | Không có health check | không có `/health`, `/ready` (gọi `/health` ra 404) | Platform không biết agent còn sống hay đã treo để restart, load balancer không biết có nên gửi traffic vào không |
| 6 | Bind `localhost` | `host="localhost"` (dòng 51) | Trong container chỉ nhận kết nối từ chính container, bên ngoài không gọi vào được |
| 7 | Port cố định | `port=8000` (dòng 52) | Railway/Render cấp port qua biến `PORT`, app không đọc thì platform không route được |
| 8 | Bật `reload=True` | dòng 53 | Tốn tài nguyên để theo dõi file, sinh thêm process con, không dùng cho production |
| 9 | Không xử lý SIGTERM | không có handler, không có lifespan | Platform tắt container là request đang chạy bị cắt ngang, không có bước dọn kết nối |
| 10 | Không validate input | `question: str` nhận qua query string, không kiểm tra rỗng hay độ dài | Câu hỏi rỗng hoặc rất dài vẫn được gửi thẳng tới LLM, tốn tiền và dễ bị lạm dụng |

### Exercise 1.2 — Kết quả chạy bản develop

Chạy bằng `python app.py` trong `01-localhost-vs-production/develop/`.

```text
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 422 Unprocessable Entity
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}

$ curl -i http://localhost:8000/health
HTTP/1.1 404 Not Found
```

Log của server, lộ cả API key:

```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.
INFO:     127.0.0.1:56382 - "POST /ask?question=Hello HTTP/1.1" 200 OK
```

**Quan sát:** app có chạy nhưng chưa sẵn sàng cho production.
- Lần chạy đầu, khi output của server được ghi ra file trên Windows, `/ask` trả **500 Internal Server Error**: `print(f"[DEBUG] Response: {response}")` ném `UnicodeEncodeError: 'charmap' codec can't encode character 'Đ'` vì console dùng cp1252, không in được tiếng Việt. Phải đặt `PYTHONIOENCODING=utf-8` mới chạy được. Đây là ví dụ thật của "works on my machine": cùng code nhưng hành vi đổi theo môi trường chạy.
- Không có `/health` (404), app chỉ nghe `localhost`, nhận `question` qua query string nên gửi JSON bị 422.

### Exercise 1.3 — So sánh develop và production

Bản production chạy bằng `cp .env.example .env && python app.py`:

```text
$ curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":1.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:39:18.277633+00:00"}
$ curl http://localhost:8000/ready
{"ready":true}
```

| Tiêu chí | Develop | Production | Vì sao quan trọng |
| --- | --- | --- | --- |
| Config | Hardcode trong code (`DEBUG = True`, `MAX_TOKENS = 500`) | Đọc từ biến môi trường trong `config.py` (`os.getenv("DEBUG", "false")`…) | Một image dùng được cho dev/staging/prod, chỉ đổi biến môi trường, không phải sửa code (12-factor: Config) |
| Secrets | `OPENAI_API_KEY = "sk-..."` trong code | `os.getenv("OPENAI_API_KEY")`, `.env` nằm trong `.gitignore`, chỉ commit `.env.example` | Secret không vào git nên không bị lộ khi push. Đổi key không cần deploy lại code |
| Fail fast | Không kiểm tra gì | `validate()` ném lỗi nếu `ENVIRONMENT=production` mà thiếu `AGENT_API_KEY` | Thiếu cấu hình quan trọng thì app dừng ngay lúc khởi động, không chạy ở trạng thái thiếu bảo mật |
| Health check | Không có, `/health` → 404 | `/health` (liveness) và `/ready` (readiness, trả 503 khi chưa sẵn sàng) | Platform dựa vào `/health` để restart container bị treo, load balancer dựa vào `/ready` để chỉ gửi traffic vào instance đã sẵn sàng |
| Logging | `print()`, in cả secret | Logging JSON có level, chỉ log độ dài câu hỏi, không log secret | Log có cấu trúc thì parse và search được trong Loki/Datadog. Không log secret thì đọc log không làm lộ key |
| Shutdown | Tắt đột ngột | `lifespan` đặt `is_ready = False` rồi chờ request đang chạy xong, thêm handler SIGTERM | Khi platform tắt hoặc deploy lại, request đang xử lý không bị cắt ngang, kết nối được đóng gọn |
| Host / Port | `localhost:8000` cứng | `HOST=0.0.0.0`, `PORT` lấy từ env | Trong container phải bind `0.0.0.0` mới nhận được traffic từ ngoài. Cloud cấp port qua `PORT` |
| Reload | `reload=True` luôn bật | `reload=settings.debug`, chỉ bật khi `DEBUG=true` | Không tốn tài nguyên và không sinh process thừa khi chạy production |
| Input | Query string, không kiểm tra | JSON body, câu hỏi rỗng → 422 kèm thông báo rõ ràng | Client biết mình gửi sai ở đâu. Không gửi request rác tới LLM |
| CORS | Không cấu hình | `ALLOWED_ORIGINS` từ env | Chỉ frontend được phép mới gọi được API từ trình duyệt |

**Nhận xét thêm:** bản production vẫn có một điểm chưa đúng. `config.py` gọi `logging.warning(...)` trước khi `app.py` gọi `logging.basicConfig(...)`, nên root logger đã được cấu hình với format mặc định và level WARNING. Kết quả là log khi chạy hiện `WARNING:root:OPENAI_API_KEY not set — using mock LLM`, không phải JSON, còn các log `INFO` như `agent_request` không xuất hiện. Cách sửa: cấu hình logging trước khi import `config`, hoặc gọi `logging.basicConfig(..., force=True)`.

## Part 2 — Docker

### Exercise 2.1 — Câu hỏi về Dockerfile (`02-docker/develop/Dockerfile`)

1. **Base image là gì?** `python:3.11`, bản Python đầy đủ chạy trên Debian, có sẵn gcc, git và nhiều thư viện hệ thống. Vì vậy image rất nặng (đo ở 2.3).
2. **Working directory là gì?** `/app` (`WORKDIR /app`). Các lệnh `COPY`, `RUN`, `CMD` phía sau đều chạy tương đối với thư mục này.
3. **Vì sao `COPY requirements.txt` đứng trước?** Docker cache theo từng layer, layer nào thay đổi thì nó và mọi layer phía sau phải build lại. Code `app.py` đổi thường xuyên, còn `requirements.txt` hiếm khi đổi. Copy `requirements.txt` rồi `pip install` trước thì khi chỉ sửa code, layer cài dependency vẫn lấy từ cache và build chỉ mất vài giây. Nếu `COPY . .` trước thì sửa một dòng code cũng phải cài lại toàn bộ dependency.
4. **CMD và ENTRYPOINT khác nhau thế nào?**
   - `CMD` là lệnh mặc định, bị thay hoàn toàn khi truyền lệnh khác vào `docker run` (ví dụ `docker run my-agent:develop python -c "print(1)"`).
   - `ENTRYPOINT` là chương trình luôn chạy. Tham số của `docker run` (hoặc `CMD`) chỉ được nối thêm vào sau nó, muốn đổi phải dùng `--entrypoint`.
   - Hay dùng chung: `ENTRYPOINT ["uvicorn"]` với `CMD ["app:app", "--port", "8000"]` thì cố định chương trình nhưng vẫn đổi được tham số mặc định. Dockerfile này chỉ dùng `CMD ["python", "app.py"]`.

### Exercise 2.2 — Build và chạy container

```text
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .     # build từ gốc repo, mất 1m53s
$ docker run -d --rm --name k5-dev -p 8000:8000 my-agent:develop

$ curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"
HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"What is Docker?"}'
HTTP/1.1 422 Unprocessable Entity          # bản develop nhận question qua query, không nhận JSON

$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":1.4,"container":true}
```

Log container (`docker logs k5-dev`):

```text
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     172.17.0.1:57100 - "POST /ask?question=What%20is%20Docker%3F HTTP/1.1" 200 OK
```

Request đến từ `172.17.0.1`, tức gateway của bridge network Docker. App phải bind `0.0.0.0` mới nhận được (bản Part 1 bind `localhost` sẽ không gọi được từ ngoài container).

### Exercise 2.3 — Multi-stage build (`02-docker/production/Dockerfile`)

- **Stage 1 (`builder`):** từ `python:3.11-slim`, cài thêm `gcc` và `libpq-dev` (công cụ để compile package có phần C), rồi `pip install --user -r requirements.txt` vào `/root/.local`. Stage này chỉ dùng để build và không được deploy.
- **Stage 2 (`runtime`):** bắt đầu lại từ `python:3.11-slim` sạch. Tạo user không phải root `appuser`, chỉ `COPY --from=builder /root/.local` (các package đã cài), `main.py` và `utils/mock_llm.py`, chuyển sang `USER appuser`, thêm `HEALTHCHECK` và chạy `uvicorn` với 2 worker.
- **Vì sao image nhỏ hơn?**
  1. Base `python:3.11-slim` (189 MB) thay cho `python:3.11` (bản full, hơn 1 GB).
  2. `gcc`, `libpq-dev`, cache của apt và pip chỉ nằm ở stage builder, không vào image cuối. Image cuối chỉ thêm một layer 40.8 MB chứa các package Python (theo `docker history`).
  3. Chỉ copy đúng 2 file code cần chạy, không copy cả thư mục.
  Ngoài ra chạy bằng non-root user nên an toàn hơn khi container bị khai thác.

Đo bằng `docker images my-agent` (Docker Desktop 29.9.2):

```text
IMAGE               ID             DISK USAGE   CONTENT SIZE
my-agent:advanced   1ba8dd93ea14        240MB         57.4MB
my-agent:develop    bb00416e95bf       1.67GB          426MB
```

| Image | Disk usage | Content size (nén) | Byte chính xác (`docker image inspect`) |
| --- | ---: | ---: | ---: |
| `my-agent:develop` (single-stage, `python:3.11`) | 1.67 GB | 426 MB | 1 667 784 124 |
| `my-agent:advanced` (multi-stage, `python:3.11-slim`) | 240 MB | 57.4 MB | 239 815 302 |
| **Chênh lệch** | **nhỏ hơn 85.6%** (≈ 7 lần) | **nhỏ hơn 86.5%** | |

Cách tính: `(1667784124 − 239815302) / 1667784124 = 85.6%`; `(426 − 57.4) / 426 = 86.5%`.

Ghi chú: lúc build, Docker Hub trả `429 Too Many Requests` khi pull `python:3.11-slim` (vượt giới hạn pull ẩn danh). Mình pull cùng image từ mirror chính thức `mirror.gcr.io/library/python:3.11-slim` rồi `docker tag` lại thành `python:3.11-slim`, Dockerfile giữ nguyên.

### Exercise 2.4 — Docker Compose stack (`02-docker/production/docker-compose.yml`)

Chạy bằng `touch .env.local && docker compose -p k5-day14-docker up -d --build`. Có 4 service:

```text
                 Client (curl / trình duyệt)
                            │  HTTP :80 (và :443)
                            ▼
              ┌───────────────────────────────┐
              │ nginx (nginx:alpine)           │  cổng duy nhất mở ra host
              │ reverse proxy, load balancer,  │
              │ rate limit 10 r/s, security    │
              │ headers                        │
              └───────────────┬───────────────┘
                              │ proxy_pass http://agent:8000
         ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ network "internal" (bridge) ─ ─ ─
                              ▼
              ┌───────────────────────────────┐
              │ agent (FastAPI, build từ        │  không mở port ra host
              │ Dockerfile, target: runtime)    │
              └───────┬───────────────┬───────┘
     REDIS_URL=        │               │  QDRANT_URL=
     redis://redis:6379/0              │  http://qdrant:6333
                      ▼               ▼
        ┌─────────────────────┐ ┌─────────────────────┐
        │ redis:7-alpine       │ │ qdrant:v1.9.0        │
        │ cache, session,      │ │ vector DB cho RAG    │
        │ rate limit           │ │                      │
        │ volume: redis_data   │ │ volume: qdrant_data  │
        └─────────────────────┘ └─────────────────────┘
```

**Các service giao tiếp thế nào:**
- Cả 4 service nằm chung network `internal`, gọi nhau bằng **tên service** nhờ DNS nội bộ của Docker (`agent`, `redis`, `qdrant`).
- Chỉ `nginx` publish cổng ra host (80, 443). `agent` không publish cổng, mọi request phải đi qua Nginx.
- Thứ tự khởi động theo `depends_on`: `redis` và `qdrant` phải `service_healthy` trước thì `agent` mới start, sau đó mới tới `nginx`.
- Dữ liệu Redis và Qdrant nằm trong named volume nên container bị xoá và tạo lại thì dữ liệu vẫn còn (trừ khi chạy `down -v`).

Trạng thái sau khi `up`:

```text
SERVICE   IMAGE                   STATUS                    PORTS
agent     k5-day14-docker-agent   Up 5 seconds (healthy)    8000/tcp
nginx     nginx:alpine            Up 5 seconds              0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
qdrant    qdrant/qdrant:v1.9.0    Up 16 seconds (healthy)   6333-6334/tcp
redis     redis:7-alpine          Up 16 seconds (healthy)   6379/tcp
```

Test qua Nginx:

```text
$ curl -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":10.8,"version":"2.0.0","timestamp":"2026-11-26T07:53:29.195863"}

$ curl -i http://localhost/ask -X POST -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

$ curl -m 3 -o /dev/null -w '%{http_code}\n' http://localhost:8000/health
000        # agent không mở cổng ra host, chỉ vào được qua Nginx
```

- Header `Server: nginx` (đã ẩn version nhờ `server_tokens off`) và các security header cho thấy request đã đi qua Nginx rồi mới tới agent.
- Log agent là JSON: `{"time":"2026-11-26 07:53:38,229","level":"INFO","msg":"{"event": "request", "q_len": 2}"}`. Chỉ log độ dài câu hỏi, không log nội dung.
- Debug container: `docker compose -p k5-day14-docker logs agent` để xem log, `docker compose -p k5-day14-docker exec agent sh` để vào trong container.
- Dọn stack: `docker compose -p k5-day14-docker down -v`.

## Part 3 — Cloud Deployment

### Exercise 3.1 / 3.2 — URL public

Nền tảng chính: **Railway**. Deploy chính agent Part 6 (`06-lab-complete/`), chi tiết trong [DEPLOYMENT.md](DEPLOYMENT.md).

- URL public: **https://agent-production-8b9dae17.up.railway.app**
- 2 service trên Railway: `agent` (build từ `06-lab-complete/Dockerfile`) và `Redis` (nối qua `REDIS_URL=${{Redis.REDIS_URL}}`). `AGENT_API_KEY` đặt bằng biến môi trường trên Railway.
- Kết quả 4 lệnh tự kiểm ở CP6 (2026-11-26):

```text
GET /health            200 (expected 200) OK
GET /ready             200 (expected 200) OK
POST /ask (no key)     401 (expected 401) OK
POST /ask (with key)   200 (expected 200) OK
```

Trên cloud, rate limit cũng chạy đúng: request thứ 11 trong một phút trả `429` kèm `retry-after: 43`. Script chấm `--public-url` báo `✅ Public URL: GET .../health → 200`.

### So sánh `railway.toml` và `render.yaml` (`06-lab-complete/`)

| Khía cạnh | `railway.toml` | `render.yaml` | Vì sao khác |
| --- | --- | --- | --- |
| Bản chất | File **config-as-code cho một service**: chỉ mô tả cách build và chạy service chứa file | **Blueprint (IaC) cho cả hệ thống**: khai báo nhiều service (web + Key Value) và quan hệ giữa chúng | Railway tạo project/service/database qua dashboard hoặc CLI rồi gắn file config vào service. Render dựng toàn bộ hạ tầng từ một file |
| Build | `[build] builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"` | `runtime: docker`, `dockerContext: ./06-lab-complete`, `dockerfilePath: ./06-lab-complete/Dockerfile` | `railway up` chạy ngay trong `06-lab-complete/` nên đường dẫn tương đối. Render đọc repo từ GitHub nên đường dẫn tính từ gốc repo |
| Start command | Không khai báo, dùng `CMD` của Dockerfile (`--port ${PORT:-8000}`) | Không khai báo, dùng `CMD` của Dockerfile | Cả hai platform đều cấp `PORT` qua env. Dùng Dockerfile thì một chỗ định nghĩa cách chạy cho mọi nơi |
| Health check | `[deploy] healthcheckPath = "/health"`, `healthcheckTimeout = 60` | `healthCheckPath: /health` | Railway dùng health check để quyết định deploy mới có được nhận traffic không. Render dùng cho cả deploy lẫn theo dõi định kỳ, fail thì restart |
| Restart | `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3` | Không có field, Render tự restart | Railway cho chỉnh chính sách restart, Render quản lý tự động |
| Redis | **Không có** trong file: tạo Redis service riêng trên Railway rồi đặt `REDIS_URL=${{Redis.REDIS_URL}}` (biến tham chiếu) | Khai báo luôn `type: keyvalue` và nối bằng `fromService: {type: keyvalue, name: day14-redis, property: connectionString}` | Do khác biệt "config 1 service" và "IaC cả hệ thống" ở dòng đầu |
| Secret | Không có trong file: đặt bằng `railway variables --set` hoặc dashboard | `AGENT_API_KEY: generateValue: true` (Render tự sinh), có thể dùng `sync: false` để nhập tay trên dashboard | Cả hai đều không để secret trong git. Render cần cú pháp riêng vì env nằm ngay trong file commit lên repo |
| Env thường | Không có trong file | `ENVIRONMENT`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD` ghi thẳng | Giá trị không bí mật thì Render cho ghi vào Blueprint để tái tạo được hạ tầng |
| Plan / free tier | Không khai báo, gói theo tài khoản (credit dùng thử) | `plan: free` cho cả web lẫn Key Value | Render chọn gói theo từng service. Gói free của Render ngủ sau 15 phút không có traffic (cold start khoảng 1 phút), Railway thì không |

So với bản mẫu trong `03-cloud-deployment/`: bản mẫu Railway dùng `builder = "NIXPACKS"` + `startCommand`, bản mẫu Render dùng `runtime: python` + `buildCommand`/`startCommand` (platform tự build Python). Bản của mình build bằng **Dockerfile** để image chạy trên cloud giống hệt image đã kiểm bằng `check_production_ready.py` (multi-stage, non-root, uvicorn là PID 1).

### Exercise 3.3 — Pipeline Cloud Run (`03-cloud-deployment/production-cloud-run/`)

`cloudbuild.yaml` là pipeline CI/CD 4 bước của Cloud Build, chạy khi push lên `main`:
1. **test**: trong `python:3.11-slim`, cài `requirements.txt` + `pytest` rồi chạy `pytest tests/`. Test fail thì pipeline dừng, không build.
2. **build**: `docker build` gắn 2 tag `gcr.io/$PROJECT_ID/ai-agent:$COMMIT_SHA` và `:latest`, dùng `--cache-from :latest` để tận dụng layer cache.
3. **push**: đẩy cả 2 tag lên Container Registry.
4. **deploy**: `gcloud run deploy ai-agent` với đúng image `:$COMMIT_SHA` (truy vết được commit, rollback bằng cách deploy lại SHA cũ) ở `asia-southeast1`, `min-instances=1` (tránh cold start), `max-instances=10`, 512Mi/1 CPU, timeout 60s, secret `OPENAI_API_KEY` lấy từ **Secret Manager** (`--set-secrets`) chứ không nằm trong code.

`service.yaml` mô tả cùng service đó dạng IaC (Knative, deploy bằng `gcloud run services replace`): autoscale 1–10 instance, `containerConcurrency: 80`, `AGENT_API_KEY` và `OPENAI_API_KEY` lấy qua `secretKeyRef`, `livenessProbe` gọi `/health` mỗi 30s và `startupProbe` gọi `/ready` (tối đa 10 lần × 3s) trước khi nhận traffic.

## Part 4 — API Security

### Exercise 4.1 — API key (`04-api-gateway/develop/app.py`)

- **Key được kiểm tra ở đâu?** Trong dependency `verify_api_key` (dòng 39–54). Hàm này đọc header `X-API-Key` qua `APIKeyHeader(name="X-API-Key", auto_error=False)` rồi so với `API_KEY = os.getenv("AGENT_API_KEY", ...)`. Endpoint `/ask` khai báo `_key: str = Depends(verify_api_key)` nên FastAPI chạy hàm này trước khi vào handler. `/` và `/health` không có dependency nên vẫn public, vì platform cần gọi `/health` mà không có key.
- **Sai key thì sao?** Thiếu header thì trả **401** `Missing API key`. Có header nhưng sai thì trả **403** `Invalid API key.`. Request bị chặn trước khi gọi LLM nên không tốn tiền. Lưu ý: tiêu chí Part 6 yêu cầu cả thiếu và sai key đều trả **401**, khác bản mẫu này.
- **Rotate key thế nào?** Key đọc từ biến môi trường `AGENT_API_KEY`, nên rotate không cần sửa code: đặt giá trị mới trên platform (hoặc secret manager), restart hoặc redeploy, rồi báo client dùng key mới. Muốn không có downtime thì cho server nhận cùng lúc key cũ và key mới trong một thời gian (ví dụ `AGENT_API_KEYS=new,old`), client đổi xong mới gỡ key cũ.
- **Điểm chưa tốt của bản mẫu:** có giá trị mặc định `"demo-key-change-in-production"` (quên đặt env là chạy với key ai cũng biết), dòng 91 `print(f"API Key: {API_KEY}")` in key ra log, và so sánh bằng `!=` thay vì `hmac.compare_digest` (có thể bị timing attack).

Chạy `AGENT_API_KEY=secret-key-123 python app.py`:

```text
$ curl -i http://localhost:8000/ask -X POST -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i http://localhost:8000/ask -X POST -H "X-API-Key: wrong-key" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 403 Forbidden
content-type: application/json

{"detail":"Invalid API key."}

$ curl -i http://localhost:8000/ask -X POST -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 — JWT (`04-api-gateway/production/auth.py`)

**Luồng JWT:**
1. Client gửi `POST /auth/token` với username/password. `authenticate_user` kiểm tra với `DEMO_USERS`, sai thì 401.
2. `create_token` tạo payload `{sub, role, iat, exp = now + 60 phút}` và ký bằng HS256 với `JWT_SECRET` (đọc từ env).
3. Client gửi token trong header `Authorization: Bearer <token>` ở mọi request sau.
4. `verify_token` kiểm tra chữ ký và hạn bằng `jwt.decode`. Thiếu token → 401, token hết hạn → 401, token bị sửa hoặc sai chữ ký → 403. Hợp lệ thì trả `{username, role}` cho endpoint.

Ưu điểm là **stateless**: server không phải tra DB hay session mỗi request, chỉ cần verify chữ ký, nên instance nào cũng xác thực được. Đổi lại, token đã phát thì không thu hồi được trước khi hết hạn (trừ khi thêm blacklist), và payload chỉ được mã hoá base64 chứ không mã hoá bí mật, nên không được đặt dữ liệu nhạy cảm vào. Bản mẫu có `JWT_SECRET` mặc định trong code, production phải đặt qua env.

```text
$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"wrong"}'
HTTP/1.1 401 Unauthorized
{"detail":"Invalid credentials"}

$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
HTTP/1.1 200 OK
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"access_token":"eyJ***REDACTED***","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer eyJ***REDACTED***"}
```

Phần payload của token sau khi decode base64 (không cần secret cũng đọc được):

```text
{"sub":"student","role":"user","iat":1795679790,"exp":1795683390}      # exp - iat = 3600s = 60 phút
```

```text
$ curl -i http://localhost:8000/ask -X POST -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

$ curl -i http://localhost:8000/ask -X POST -H "Authorization: Bearer abc.def.ghi" -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid token."}

$ curl -i http://localhost:8000/ask -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"question":""}'
HTTP/1.1 422 Unprocessable Entity
{"detail":[{"type":"string_too_short","loc":["body","question"],"msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}}]}
```

Phân quyền theo role: `student` gọi `/admin/stats` → `403 {"detail":"Admin only"}`, `teacher` (role `admin`) gọi được.

### Exercise 4.3 — Rate limiting (`04-api-gateway/production/rate_limiter.py`)

- **Thuật toán:** **sliding window log**. Mỗi user có một `deque` lưu timestamp các request. Mỗi lần gọi, xoá timestamp cũ hơn 60 giây, nếu còn ≥ `max_requests` thì trả 429, không thì thêm timestamp hiện tại. Docstring gọi là "Sliding Window Counter" nhưng code thực ra lưu từng timestamp, tức là window log: chính xác nhưng tốn bộ nhớ tỉ lệ với số request.
- **Giới hạn:** user thường **10 request/60 giây** (`rate_limiter_user`), admin **100 request/60 giây** (`rate_limiter_admin`).
- **Bypass cho admin:** `app.py` chọn limiter theo role trong JWT: `limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`. Admin không bị bỏ hẳn giới hạn mà có hạn mức cao hơn. Muốn bypass hoàn toàn thì bỏ qua `limiter.check()` khi `role == "admin"`.
- **Hạn chế:** state nằm trong RAM của process. Chạy nhiều instance thì mỗi instance đếm riêng (3 instance = 30 request/phút), restart là mất. Production phải lưu trong Redis (ví dụ sorted set `ZADD` / `ZREMRANGEBYSCORE` / `ZCARD`), đây cũng là yêu cầu của Part 6.

Vòng lặp 12 request với token của `student` (lấy ở 4.2):

```text
$ for i in $(seq 1 12); do curl -s -i http://localhost:8000/ask -X POST -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" -d "{\"question\": \"Test $i\"}"; done
--- request 1
HTTP/1.1 200 OK
{"question":"Test 1","answer":"Đây là câu trả lời từ AI agent (mock). ...","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}
--- request 2
HTTP/1.1 200 OK
{"question":"Test 2", ... "usage":{"requests_remaining":8,"budget_remaining_usd":4e-05}}
...
--- request 10
HTTP/1.1 200 OK
{"question":"Test 10", ... "usage":{"requests_remaining":0,"budget_remaining_usd":0.000186}}
--- request 11
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795679855
retry-after: 57
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":57}}
--- request 12
HTTP/1.1 429 Too Many Requests
retry-after: 56
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":56}}
```

Request 1–10 trả 200, `requests_remaining` giảm từ 9 về 0. Từ request 11 trả **429** kèm `Retry-After` để client biết bao lâu nữa thử lại. Cùng lúc đó `teacher` (admin) gọi 15 request liên tiếp đều 200, vì hạn mức admin là 100/phút.

### Exercise 4.4 — Cost guard

**Bản mẫu `cost_guard.py` làm gì:**
- Đếm token input/output của từng user theo **ngày** và quy ra USD theo giá GPT-4o-mini ($0.15 / 1M input, $0.60 / 1M output).
- `check_budget()` chạy **trước** khi gọi LLM: vượt budget toàn hệ thống ($10/ngày) → 503; vượt budget của user ($1/ngày) → **402 Payment Required**; dùng ≥ 80% thì log cảnh báo.
- `record_usage()` chạy **sau** khi gọi LLM để cộng số token thực tế.
- `/me/usage` sau 10 request của `student`: `{"requests":10,"input_tokens":40,"output_tokens":300,"cost_usd":0.000186,"budget_usd":1.0,"budget_remaining_usd":0.999814}`.
- Hạn chế: lưu trong RAM (nhiều instance thì mỗi cái đếm riêng, restart mất số liệu). Ngoài ra trong `/ask`, field `budget_remaining_usd` thực ra trả `usage.total_cost_usd` (số đã **dùng**, không phải số **còn lại**), đây là bug đặt tên của bản mẫu.

**Rate limit và cost guard khác nhau:** rate limit chặn **tốc độ** (10 request/phút), cost guard chặn **tổng tiền**. Cần cả hai: một user có thể gọi đều 10 request/phút suốt cả ngày (không vi phạm rate limit) với prompt rất dài và vẫn đốt hết tiền. Ngược lại, cost guard một mình không ngăn được một đợt spam làm quá tải server.

**Cài đặt theo đề (budget $10/tháng, lưu trong Redis, reset đầu tháng):** file [04-api-gateway/production/budget_redis.py](04-api-gateway/production/budget_redis.py).

```python
MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10"))
KEY_TTL_SECONDS = 32 * 24 * 3600

_CHECK_AND_SPEND = r.register_script("""
    local current = tonumber(redis.call('GET', KEYS[1]) or '0')
    local cost = tonumber(ARGV[1])
    if current + cost > tonumber(ARGV[2]) then
        return 0
    end
    redis.call('INCRBYFLOAT', KEYS[1], cost)
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
    return 1
""")

def _budget_key(user_id: str) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"budget:{user_id}:{month}"

def check_budget(user_id: str, estimated_cost: float) -> bool:
    if estimated_cost < 0:
        raise ValueError("estimated_cost must be >= 0")
    ok = _CHECK_AND_SPEND(keys=[_budget_key(user_id)],
                          args=[estimated_cost, MONTHLY_BUDGET_USD, KEY_TTL_SECONDS])
    return ok == 1
```

Cách làm:
- **Reset đầu tháng:** key chứa tháng (`budget:<user>:2026-11`). Sang tháng 12 code tự đọc key `...:2026-12` chưa tồn tại, tức chi tiêu bằng 0. Không cần cron job reset.
- **Dọn key cũ:** `EXPIRE` 32 ngày, dài hơn tháng dài nhất, nên key tháng cũ tự bị Redis xoá.
- **Đúng khi chạy nhiều instance:** khác với lời giải mẫu trong `CODE_LAB.md` (`GET` rồi mới `INCRBYFLOAT`, hai bước riêng), mình gộp kiểm tra và cộng tiền vào **một Lua script**. Redis chạy script nguyên khối nên hai request đồng thời không thể cùng đọc "còn $1" rồi cùng được cho qua.
- **Budget đọc từ env** (`MONTHLY_BUDGET_USD`), không hardcode. Khi `check_budget` trả `False`, endpoint trả 402.

Chạy thử với Redis tạm (`docker run -d --rm -p 6379:6379 redis:7-alpine`, rồi `python budget_redis.py`):

```text
request 1: cost $3.00 -> OK   spent=$3.00
request 2: cost $3.00 -> OK   spent=$6.00
request 3: cost $3.00 -> OK   spent=$9.00
request 4: cost $3.00 -> BLOCKED (402)  spent=$9.00
request 5: cost $3.00 -> BLOCKED (402)  spent=$9.00
key=budget:demo-user:2026-11 ttl=2764800s
```

Request bị chặn không bị cộng tiền (vẫn $9.00). TTL = 2 764 800 s = 32 ngày.

Thử race condition: 50 thread gọi đồng thời, mỗi lần $0.50, budget $10:

```text
concurrent: 20 allowed / 50, spent=$10.00
```

Đúng 20 × $0.50 = $10.00 được cho qua, không vượt budget.

## Part 5 — Scaling & Reliability

### Exercise 5.1 — Health check (`05-scaling-reliability/develop/app.py`)

Hai endpoint đã có trong bản develop:

```python
@app.get("/health")
def health():
    # Liveness: process còn sống. Trả 200 kèm uptime, version và check bộ nhớ (psutil),
    # status = "degraded" nếu RAM > 90% nhưng vẫn là HTTP 200.
    ...

@app.get("/ready")
def ready():
    # Readiness: chỉ nhận traffic khi đã khởi động xong và chưa shutdown.
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Agent not ready. Check back in a few seconds.")
    return {"ready": True, "in_flight_requests": _in_flight_requests}
```

```text
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.6,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T08:01:04.713943+00:00","checks":{"memory":{"status":"ok","used_percent":76.8}}}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

`in_flight_requests` bằng 1 vì middleware đếm luôn chính request `/ready` đang chạy.

**Liveness và readiness khác nhau thế nào:**

| | `/health` (liveness) | `/ready` (readiness) |
| --- | --- | --- |
| Câu hỏi | Process còn sống không? | Có nên gửi traffic vào instance này không? |
| Ai gọi | Platform, Docker `HEALTHCHECK` | Load balancer, Kubernetes, Nginx |
| Khi fail | **Restart** container | **Ngừng gửi traffic**, không restart |
| Có kiểm tra dependency không | Không. Redis chết thì restart agent cũng không chữa được, chỉ tạo vòng restart vô ích | Có (Redis, DB). Mất dependency thì trả 503 |

Bản develop chỉ dựa vào cờ `_is_ready`, chưa kiểm tra dependency. Bản production (`05-scaling-reliability/production/app.py`) `/ready` gọi `_redis.ping()` và trả 503 khi Redis không trả lời, còn `/health` vẫn trả 200 với `"status":"degraded"`. Mình đã thử bằng cách tắt Redis ở Exercise 5.4.

### Exercise 5.2 — Graceful shutdown

Signal handler theo đề:

```python
import signal

def shutdown_handler(signum, frame):
    """Handle SIGTERM from container orchestrator"""
    global _is_ready
    _is_ready = False          # 1. /ready trả 503 → load balancer ngừng gửi request mới
    logger.info(f"Received signal {signum}, draining {_in_flight_requests} in-flight requests")
    # 2 + 3 + 4: để uvicorn đóng socket, chờ request đang chạy (tối đa
    # timeout_graceful_shutdown=30s), chạy phần shutdown của lifespan (đóng kết nối) rồi thoát.

signal.signal(signal.SIGTERM, shutdown_handler)
```

Bản develop dùng đúng cơ chế này: `uvicorn.run(..., timeout_graceful_shutdown=30)`, phần sau `yield` trong `lifespan` đặt `_is_ready = False` và chờ `_in_flight_requests` về 0 (tối đa 30 giây).

**Test thật.** Python trên Windows không gửi được SIGTERM, nên mình chạy `develop/app.py` trong container `python:3.11-slim`, với `python app.py` là PID 1. Mock LLM ở bài này mất 3 giây cho mỗi câu. Gửi một request `/ask`, 0.5 giây sau gửi `docker kill -s TERM`, 0.3 giây sau nữa gửi thêm một request mới:

```text
[test] sending SIGTERM at 15:02:15.243
[test] new request during shutdown:
000                                                    # request mới bị từ chối kết nối
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
[client] HTTP 200 after 3.028022s                      # request đang chạy vẫn hoàn thành
```

Log container:

```text
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Shutting down
INFO:     172.17.0.1:46026 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-26 08:02:17,770 INFO 🔄 Graceful shutdown initiated...
2026-11-26 08:02:17,770 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [1]
2026-11-26 08:02:17,770 INFO Received signal 15 — uvicorn will handle graceful shutdown
exit code: 0
```

**Quan sát:**
1. **Request đang chạy hoàn thành:** SIGTERM đến ở giây 0.5 nhưng client vẫn nhận 200 sau 3.03 giây. Uvicorn in `Shutting down` rồi chờ request `/ask` xong mới chạy phần shutdown của lifespan.
2. **Ngừng nhận request mới:** request gửi lúc đang shutdown bị từ chối (`000`, tức connection refused), vì uvicorn đóng socket nghe ngay khi nhận SIGTERM.
3. **Thoát sạch:** exit code 0, không phải 137 (SIGKILL). Nếu không xử lý SIGTERM, Docker chờ hết 10 giây rồi SIGKILL, request đang chạy bị cắt ngang.
4. **Điểm đáng chú ý:** dòng `Received signal 15` của `handle_sigterm` in ra **sau cùng**. Lý do: khi chạy, uvicorn cài handler riêng đè lên handler của app, đến khi tắt xong mới gọi lại handler gốc. Vì vậy logic dọn dẹp nên đặt trong phần shutdown của `lifespan`, không đặt trong signal handler.
5. Trong Docker, app phải là PID 1 hoặc được `exec` (Dockerfile dùng `CMD ["python", ...]` dạng exec). Nếu chạy qua `sh -c "python app.py"` mà không có `exec` thì SIGTERM tới `sh` chứ không tới Python.

### Exercise 5.3 — Stateless (`05-scaling-reliability/production/app.py`)

**Vì sao state trong RAM hỏng khi scale:** mỗi instance có bộ nhớ riêng. Nếu `conversation_history = {}` nằm trong RAM, request 1 của user A đến instance 1 (lưu history ở đó), request 2 đến instance 2 thì instance 2 không thấy gì, nên agent "quên" cuộc hội thoại. Ngoài ra instance restart hoặc bị scale down là mất hết state.

**Bản production đã refactor:**
- Toàn bộ session lưu trong Redis: `save_session()` dùng `SETEX session:<id> 3600 <json>` (TTL 1 giờ), `load_session()` dùng `GET`.
- Client gửi `session_id`, nên **instance nào cũng phục vụ được**, response có `served_by` để thấy rõ.
- History giữ tối đa 20 message để key không phình to mãi.
- Instance không giữ gì quan trọng, nên kill hay thêm instance lúc nào cũng được.

```python
# ❌ Trước: state trong RAM của từng instance
conversation_history = {}
history = conversation_history.get(session_id, [])

# ✅ Sau: state trong Redis, dùng chung cho mọi instance
def load_session(session_id: str) -> dict:
    data = _redis.get(f"session:{session_id}")
    return json.loads(data) if data else {}

def save_session(session_id: str, data: dict, ttl_seconds: int = 3600):
    _redis.setex(f"session:{session_id}", ttl_seconds, json.dumps(data))
```

**Vẫn còn điểm chưa stateless (mình tìm ra khi chạy 5.4):**
1. **Lặng lẽ fallback sang RAM.** Nếu lúc khởi động không ping được Redis, app chuyển sang `_memory_store` (dòng 42–45) và chạy tiếp. Khi thử, `agent-1` khởi động lại đúng lúc Redis đang tắt, nên nó báo `"storage":"in-memory"` suốt từ đó dù Redis đã bật lại. Session đi qua instance này không chia sẻ với các instance khác. Tệ hơn, `/ready` của nó vẫn trả 200 vì chỉ ping khi `USE_REDIS = True`. Production nên **fail fast** (Redis không có thì không start, hoặc `/ready` trả 503) thay vì fallback.
2. **Đọc rồi ghi không nguyên khối.** `append_to_history` làm `GET` → sửa → `SETEX`. Hai request cùng session tới hai instance cùng lúc thì một message bị mất. Nên dùng Redis list (`RPUSH` + `LTRIM` + `EXPIRE`) như gợi ý `r.lrange(f"history:{user_id}", ...)` của đề.
3. **Lỗi đếm `turn`:** `turn` được tính sau khi đã thêm câu hỏi hiện tại vào history rồi còn `+ 1`, nên lượt thứ 2 báo `"turn":3`.

### Exercise 5.4 — Scale 3 instance sau Nginx

```text
$ cd 05-scaling-reliability/production && touch .env.local
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
NAME                       STATUS                    PORTS
k5-day14-scaling-agent-1   Up 8 seconds (healthy)    8000/tcp
k5-day14-scaling-agent-2   Up 8 seconds (healthy)    8000/tcp
k5-day14-scaling-agent-3   Up 8 seconds (healthy)    8000/tcp
k5-day14-scaling-nginx-1   Up 8 seconds              0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   Up 19 seconds (healthy)   6379/tcp
```

**10 request qua Nginx (`POST http://localhost:8080/chat`):** header `X-Served-By` (Nginx thêm vào) và field `served_by` (do app trả) cho thấy Nginx chia **round-robin** đều cho 3 instance:

```text
X-Served-By: 172.21.0.4:8000 "served_by":"instance-12b24a"
X-Served-By: 172.21.0.5:8000 "served_by":"instance-e33827"
X-Served-By: 172.21.0.3:8000 "served_by":"instance-ed69d4"
X-Served-By: 172.21.0.4:8000 "served_by":"instance-12b24a"
X-Served-By: 172.21.0.5:8000 "served_by":"instance-e33827"
X-Served-By: 172.21.0.3:8000 "served_by":"instance-ed69d4"
X-Served-By: 172.21.0.4:8000 "served_by":"instance-12b24a"
X-Served-By: 172.21.0.5:8000 "served_by":"instance-e33827"
X-Served-By: 172.21.0.3:8000 "served_by":"instance-ed69d4"
X-Served-By: 172.21.0.4:8000 "served_by":"instance-12b24a"
```

`docker compose -p k5-day14-scaling logs agent` cũng cho thấy cả `agent-1`, `agent-2` và `agent-3` đều nhận `POST /chat` và đều log `Storage: Redis ✅`.

**Kill 1 instance giữa cuộc hội thoại:** tạo session, gửi 2 lượt, chạy `docker kill k5-day14-scaling-agent-1`, rồi gửi tiếp 4 lượt cùng `session_id`:

```text
### kill agent-1
k5-day14-scaling-agent-2 Up 33 seconds (healthy)
k5-day14-scaling-agent-3 Up 33 seconds (healthy)
turn 3: 200 "served_by":"instance-12b24a"
turn 4: 200 "served_by":"instance-ed69d4"
turn 5: 200 "served_by":"instance-ed69d4"
turn 6: 200 "served_by":"instance-12b24a"
history count: "count":12
```

Cả 4 lượt sau khi kill đều 200, được 2 instance còn lại phục vụ, và history đủ 12 message (6 lượt × 2). Nginx thấy lỗi kết nối tới instance chết thì chuyển request sang instance khác (`proxy_next_upstream error timeout http_503`), user không thấy lỗi.

**Tắt Redis (`docker compose -p k5-day14-scaling stop redis`):**

```text
-- /health x6 (qua Nginx)
      2 instance-12b24a redis status=degraded HTTP 200
      2 instance-badf4e in-memory status=ok HTTP 200
      2 instance-ed69d4 redis status=degraded HTTP 200
-- /ready gọi thẳng trong từng container
agent-1: 200 {"ready":true,"instance":"instance-badf4e"}
agent-2: 503 {"detail":"Redis not available"}
agent-3: 503 {"detail":"Redis not available"}
-- /ready qua Nginx x6
      6 {"ready":true,"instance":"instance-badf4e"} HTTP 200
-- /chat qua Nginx x6
      6 HTTP 200 "served_by":"instance-badf4e" "storage":"in-memory"
```

- `/health` vẫn **200** (`degraded`), nên platform không restart agent một cách vô ích.
- `/ready` của 2 instance dùng Redis trả **503**. Nginx coi 503 là lỗi (`proxy_next_upstream ... http_503`, mặc định `max_fails=1`, `fail_timeout=10s`), tạm loại 2 instance đó và dồn mọi request sang `instance-badf4e`. Đó là instance đã fallback sang RAM (điểm 1 ở 5.3), nên request vẫn 200 nhưng **session không được chia sẻ**. Đây chính là lỗi "silent degradation" mà readiness check phải chặn.
- Bật lại Redis và `docker restart k5-day14-scaling-agent-1`: cả 3 instance trở lại `"status":"ok","storage":"redis"`.

Dọn: `docker compose -p k5-day14-scaling down`.

### Exercise 5.5 — `test_stateless.py`

```text
$ python test_stateless.py
============================================================
Stateless Scaling Demo
============================================================

Session ID: a3d4f1b2-947b-463c-864c-78429c364732

Request 1: [instance-e33827]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-ed69d4]
  Q: Why do we need containers?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 3: [instance-12b24a]
  Q: What is Kubernetes?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 4: [instance-e33827]
  Q: How does load balancing work?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 5: [instance-ed69d4]
  Q: What is Redis used for?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-ed69d4', 'instance-12b24a', 'instance-e33827'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Kubernetes?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: How does load balancing work?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Redis used for?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...

✅ Session history preserved across all instances via Redis!
```

**Giải thích:** 5 câu hỏi cùng một `session_id` được 3 instance khác nhau trả lời, theo thứ tự round-robin e33827 → ed69d4 → 12b24a → e33827 → ed69d4. Không instance nào có đủ cả cuộc hội thoại trong RAM, nhưng `GET /chat/<id>/history` vẫn trả đủ **10 message** (5 câu hỏi + 5 câu trả lời, đúng thứ tự). Vậy state nằm ở Redis, không nằm trong instance. Lưu ý: script không tự kill instance nào. Phần kill instance mình đã làm riêng ở 5.4: kill `agent-1` giữa chừng, history vẫn đủ 12 message.

## Part 6 — Output `check_production_ready.py`

**Output cuối: chạy đầy đủ trong WSL Ubuntu (`os.name = posix`), Python 3.11 venv, Docker 29.9.2, 2026-11-26:**

```text
$ python check_production_ready.py
  ⏳ Khởi động agent: uvicorn app.main:app --workers 2 (Redis: container redis:7-alpine tạm thời)
  ...
✅ 1. Dockerfile (multi-stage, < 500 MB)
     ✅ Docker: build image thành công — 19s
     ✅ Docker: image < 500 MB — 273 MB
     ✅ Docker: container chạy được, GET /health → 200
✅ 7. Rate limiting
     ✅ Khi chạy: vượt giới hạn → 429 — 429 sau 5 request thành công (RATE_LIMIT_PER_MINUTE=5)
     ✅ Khi chạy: state nằm trong Redis — restart agent vẫn bị 429
✅ 8. Cost guard
     ✅ Khi chạy: hết budget → 402 — 402 ở request thứ 1
✅ 10. Structured logging
     ✅ Khi chạy: mọi dòng log của app là JSON hợp lệ — 23 dòng JSON
✅ 11. Graceful shutdown
     ✅ Code xử lý SIGTERM / lifespan shutdown
     ✅ Khi chạy: SIGTERM lúc đang có request → request vẫn 200, process tự thoát — exit code 0
     ✅ Docker: `docker stop` tắt êm (exit code 0, < 10s) — exit code 0, 0.7s

================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Ghi chú môi trường: Ubuntu 26.04 trong WSL đi kèm Python 3.14, chưa có `python3-venv` và các version ghim trong `requirements.txt` có thể chưa có wheel cho 3.14. Mình tạo venv Python 3.11 bằng `uv venv -p 3.11`. Lần chạy đầu trong WSL ra 4/12 vì Docker Desktop chưa kết nối vào WSL: không có Redis tạm nên agent trả 503 (đúng hành vi khi mất Redis). Bật WSL Integration của Docker Desktop xong thì đạt 12/12.

**Output chạy đầy đủ trên Windows (Docker Desktop 29.9.2), 2026-11-26** (để so sánh: Windows không gửi được SIGTERM):

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ⚠️  Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 11/12 tiêu chí đạt · 42/42 checks passed
  ⚠️  Chưa kiểm tra được: Graceful shutdown
```

Các dòng chi tiết đáng chú ý: `Docker: build image thành công — 46s`, `Docker: image < 500 MB — 273 MB`, `Docker: docker stop tắt êm — exit code 0, 0.7s`, `429 sau 5 request thành công (RATE_LIMIT_PER_MINUTE=5)`, `state nằm trong Redis — restart agent vẫn bị 429`, `402 ở request thứ 1`, `mọi dòng log của app là JSON hợp lệ — 23 dòng JSON`.

**Kiểm chứng tiêu chí 11 trên Linux:** chạy chính script chấm trong container `python:3.11-slim` (`os.name = posix`) với Redis trong cùng Docker network, chế độ `--skip-docker`:

```text
⚠️  11. Graceful shutdown
     ✅ Code xử lý SIGTERM / lifespan shutdown
     ✅ Khi chạy: SIGTERM lúc đang có request → request vẫn 200, process tự thoát — exit code 0
```

### Thiết kế các phần trong `06-lab-complete/`

| Tiêu chí | Cách làm |
| --- | --- |
| 1. Dockerfile | 2 stage: `builder` cài dependency vào venv `/opt/venv`, `runtime` là `python:3.11-slim` sạch, chỉ copy venv + `app/` + `utils/`. User `app` không phải root, có `HEALTHCHECK` gọi `/health` theo `PORT`. `CMD ["sh","-c","exec uvicorn ... --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}"]`: `exec` để uvicorn là PID 1 và nhận SIGTERM. Image 273 MB |
| 2. Compose | `agent` build từ Dockerfile, `REDIS_URL=redis://redis:6379/0`, `depends_on: redis (service_healthy)`, đọc `.env` với `required: false`. `redis:7-alpine` có healthcheck, AOF và volume để state rate limit/chi phí còn sau khi restart |
| 3. `.dockerignore` | Loại `.env*` (giữ `.env.example`), `__pycache__`, `venv`/`.venv`, `.git`, tài liệu, script chấm, `benchmark-observability/` |
| 4. `/health` | Chỉ trả trạng thái process (uptime, version), **không** ping Redis, nên Redis chết vẫn 200 và platform không restart agent vô ích |
| 5. `/ready` | `redis.ping()` với timeout 1s: lỗi thì **503** `{"ready":false,"reason":"redis unreachable"}`. Đang shutdown cũng trả 503. Client Redis tạo bằng `from_url` (không kết nối lúc import) nên app khởi động được khi chưa có Redis |
| 6. API key | `APIKeyHeader("X-API-Key")`, so sánh bằng `hmac.compare_digest`. Thiếu hoặc sai đều **401**. Server chưa cấu hình key thì từ chối tất cả (fail closed). `ENVIRONMENT=production` mà thiếu key thì app không khởi động |
| 7. Rate limit | Sliding window log bằng Redis sorted set, `ZREMRANGEBYSCORE → ZCARD → ZADD → PEXPIRE` gói trong **1 Lua script** để 2 worker / nhiều instance không cùng lọt qua. Vượt thì **429** + `Retry-After` + `X-RateLimit-*`. Key là `ratelimit:<sha256(api_key)[:16]>`, không lưu key thật |
| 8. Cost guard | Ước lượng token (~4 ký tự/token) × giá gpt-4o-mini. `check_budget()` chạy **trước** LLM: tổng ngày ≥ `DAILY_BUDGET_USD` (hoặc tổng tháng ≥ `MONTHLY_BUDGET_USD` nếu đặt) thì **402**. `record_cost()` chạy **sau** LLM, `INCRBYFLOAT` vào `cost:daily:<YYYY-MM-DD>` và `cost:monthly:<YYYY-MM>` có TTL, nên tự reset theo ngày/tháng |
| 9. Config | `app/config.py` đọc mọi giá trị từ env, kiểm tra kiểu và giá trị (rate limit > 0, budget ≥ 0), không có secret mặc định. `.env.example` liệt kê đủ biến |
| 10. Log JSON | `JsonFormatter` (`app/logging_setup.py`): mỗi dòng 1 JSON `{"ts","lvl","logger","event",...}`. Middleware log mỗi request (`method`, `path`, `status`, `ms`, `request_id`), không log API key hay nội dung câu hỏi. `ensure_ascii=True` để không bao giờ dính lỗi encode như Part 1. Log của uvicorn cũng chuyển sang JSON, access log mặc định bị tắt |
| 11. Shutdown | Không tự đăng ký signal handler (tránh đè handler của uvicorn, bài học từ Part 5). Uvicorn ngừng nhận request mới, chờ request đang chạy xong rồi chạy phần sau `yield` của `lifespan`: đặt `ready=False`, đóng pool Redis, log `shutdown_complete`. `docker stop` mất 0.7s, exit code 0 |
| 12. Deploy | `railway.toml`: `builder = "DOCKERFILE"`, `healthcheckPath = "/health"`. `render.yaml`: `type: web`, `runtime: docker`, `healthCheckPath: /health`, `AGENT_API_KEY` dùng `generateValue: true`, `REDIS_URL` lấy từ Key Value service. PORT do platform cấp |

**Xử lý lỗi (không lộ stack trace):**
- Body sai hoặc câu hỏi chỉ có khoảng trắng → **422** kèm thông báo rõ ràng.
- Redis mất kết nối khi gọi `/ask` → **503** `Service temporarily unavailable` + `Retry-After: 5`, thay vì 500.
- Mọi exception khác được middleware bắt → **500** `{"detail":"Internal server error","request_id":...}`. Traceback chỉ nằm trong log JSON (field `exc`), không trả cho client.

### Test tay bằng `docker compose up` (`.env` có `AGENT_API_KEY` ngẫu nhiên, che ở đây)

```text
health: 200  ready: {"ready":true,"redis":"ok"}
ask no key: {"detail":"Invalid or missing API key. Send header: X-API-Key: <key>"} 401
ask ok: {"question":"What is deployment?","answer":"Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được.","usage":{"input_tokens":4,"output_tokens":19,"cost_usd":1.2e-05,"rate_limit_remaining":9}} 200
blank q: {"detail":[{"type":"value_error","loc":["body","question"],"msg":"Value error, question must not be blank",...}]} 422
bad json: {"detail":[{"type":"json_invalid","loc":["body",1],"msg":"JSON decode error",...}]} 422
rate loop (RATE_LIMIT_PER_MINUTE=10, request thứ 1 ở trên đã dùng 1 lượt):
200 200 200 200 200 200 200 200 200 429 429 429
HTTP/1.1 429 Too Many Requests
retry-after: 58
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":58}}
### restart agent -> still 429?
429
### redis down
health: 200  ready: {"ready":false,"reason":"redis unreachable"} 503
ask: HTTP/1.1 503 Service Unavailable retry-after: 5 {"detail":"Service temporarily unavailable (storage backend unreachable)"}
ready after redis back: {"ready":true,"redis":"ok"} 200
```

Log JSON của agent:

```text
{"ts": "2026-11-26T08:14:55.788+00:00", "lvl": "INFO", "logger": "agent", "event": "startup", "version": "1.0.0", "environment": "development", "port": 8000, "rate_limit_per_minute": 10, "daily_budget_usd": 1.0, "monthly_budget_usd": null, "api_key_configured": true, "redis_ok": true}
{"ts": "2026-11-26T08:14:59.093+00:00", "lvl": "INFO", "logger": "agent", "event": "ask", "user_id": "u1", "question_chars": 19, "answer_chars": 79, "input_tokens": 4, "output_tokens": 19, "cost_usd": 1.1999999999999999e-05, "rate_limit_remaining": 9}
{"ts": "2026-11-26T08:15:29.154+00:00", "lvl": "INFO", "logger": "agent", "event": "shutdown", "detail": "in-flight requests finished, closing Redis connections"}
{"ts": "2026-11-26T08:15:29.154+00:00", "lvl": "INFO", "logger": "agent", "event": "shutdown_complete", "uptime_seconds": 25.9}
```

`docker compose stop agent` mất 1.0s, exit code 0. Dòng `startup` / `shutdown` xuất hiện 2 lần vì có 2 worker uvicorn.

## AI log

Tôi tự đọc tài liệu, chạy lệnh, viết code, đo đạc và viết câu trả lời. AI (Claude Code) chỉ được dùng như trợ lý: giải thích khái niệm, gợi ý hướng xử lý khi gặp lỗi và review lại phần tôi đã làm. Mọi số liệu và output trong bài đều do tôi chạy trên máy mình.

| Lần | Phần tôi tự làm | Hỏi AI hỗ trợ gì | Tôi kiểm tra lại thế nào |
| --- | --- | --- | --- |
| 1 | Đọc `CHECKPOINTS.md`, `RUBRIC.md`, kiểm tra môi trường CP0, lập checklist cá nhân (không nộp) | Hỏi lại cách hiểu một số tiêu chí trong rubric | Đối chiếu checklist với `CHECKPOINTS.md` và `RUBRIC.md` |
| 2 | CP1: đọc `develop/app.py` và `production/app.py`, chạy cả hai bản, tìm anti-pattern, điền Part 1 | Hỏi nguyên nhân lỗi 500 khi gửi tiếng Việt (`UnicodeEncodeError`) | Tự chạy lại curl, đối chiếu số dòng code trong `develop/app.py` |
| 3 | CP2: build 2 image, đo kích thước, chạy compose stack, vẽ sơ đồ, điền Part 2 | Hỏi cách vượt lỗi 429 rate limit của Docker Hub (gợi ý dùng `mirror.gcr.io`) | Số MB lấy từ `docker images` / `docker image inspect`, tự tính lại % |
| 4 | CP3: chạy `04-api-gateway` develop và production, test 401/403/200/429, viết cost guard Redis cho 4.4 | Nhờ review `budget_redis.py` và gợi ý dùng Lua script để tránh race condition | Chạy `budget_redis.py` với Redis tạm, thử 50 thread đồng thời để chắc không vượt $10 |
| 5 | CP4: test `/health` `/ready`, test SIGTERM trong container Linux, chạy 3 instance, `test_stateless.py`, kill instance, tắt Redis | Hỏi vì sao instance khởi động lúc Redis chết lại fallback sang RAM và lỗi đếm `turn` | Đối chiếu `served_by` và số message trong history, kiểm tra `/ready` từng container bằng `docker exec` |
| 6 | CP5: đọc `check_production_ready.py`, hoàn thành các TODO trong `06-lab-complete/` (config, auth, Redis, rate limit, cost guard, log JSON, lifespan, Dockerfile, compose, deploy config) | Hỏi cú pháp/tham khảo mẫu cho rate limit bằng Lua và cấu hình `railway.toml`, `render.yaml`; nhờ review code | Chạy script chấm `--static-only`, `--skip-docker`, bản đầy đủ (11/12 trên Windows, còn ⚠️ SIGTERM), chạy trong container Linux để kiểm tiêu chí 11, test tay 401/200/422/429, restart vẫn 429, tắt Redis → `/ready` 503, `/ask` 503 |
| 7 | CP6: so sánh `railway.toml`/`render.yaml`, mô tả pipeline Cloud Run, tự deploy lên Railway (project, Redis, biến môi trường, `railway up`, domain), viết `DEPLOYMENT.md` | Hỏi lại các lệnh Railway CLI, nhờ góp ý `smoke_test.sh` | Chạy `smoke_test.sh` với URL public (4/4 OK), thử rate limit trên cloud, xem log startup trên Railway, chạy `check_production_ready.py --public-url` |
| 8 | CP7: thêm metric `agent_question_length_chars`, chạy load test 4 mức concurrency + 3 mức `MOCK_SLOW_RATE`, eval v1/v2, thêm 2 tài liệu vào `KNOWLEDGE_BASE`, viết job CI, điền mục 1–3 `BENCHMARK_REPORT.md` | Hỏi cách viết workflow GitHub Actions và nhờ giải thích kết quả bất thường ở c=100 | Đọc lại mọi số từ file JSON, chạy lại c=100 và c=75 để loại nhiễu, kiểm tra từ khoá mới chỉ khớp 2 câu cần sửa, thử gate với v1 ra exit 1, xử lý `UnicodeEncodeError` trên Windows bằng `PYTHONUTF8=1` |
| 9 | CP8: bật stack observability, benchmark Locust scale 1/3, đọc dashboard (7.4), tìm trace chậm/lỗi (7.5), làm 5 thí nghiệm alert A–E (7.6), điền mục 4–6 `BENCHMARK_REPORT.md` | Hỏi cách sửa Dockerfile Part 7 (`PYTHONUSERBASE`), cách gọi API Prometheus/Jaeger, cách chụp màn hình bằng Chrome headless; hỏi cách xử lý khi ổ C: đầy làm Docker hỏng | Đọc số từ CSV Locust và API Prometheus, đối chiếu `trace_id` giữa Jaeger và log JSON, xem lại từng ảnh trước khi lưu; tự dọn cache npm/pip/Temp, chuyển disk Docker sang G:, kéo lại image Grafana |
