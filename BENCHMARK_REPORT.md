# Benchmark & Observability Report — Day 14

> Mọi con số lấy từ file JSON trong [`reports/`](reports/) (bản gốc ở `06-lab-complete/benchmark-observability/develop/reports/`) và CSV / ảnh trong `benchmark-results/`, `screenshots/`.

**Họ tên:** Vũ Đình Thắng — 2A202603753
**Ngày chạy:** 2026-11-26
**Môi trường:**
- Phần develop (mục 2, 3): Windows 11 Home, Intel Core i5-11400H (6 core / 12 thread), 16 GB RAM, Python 3.11.9 chạy trực tiếp trên Windows. Agent (1 process uvicorn) và `load_test.py` chạy chung một máy, gọi qua `localhost`.
- Phần production (mục 4, 5): Docker Desktop 29.9.2 (WSL2 backend) trên cùng máy.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Mock LLM mất khoảng 120–180 ms + retrieval khoảng 20 ms, p50 đo được khoảng 190–210 ms. 500 ms chừa khoảng 2.5 lần p50 cho jitter và hàng đợi, vẫn đủ nhanh cho chat. Đặt theo **p95** chứ không theo avg vì avg che tail latency (mục 2.2). Không đặt theo p99 vì mock cố ý có 3% request chậm thêm 1.5 s, nên p99 < 500 ms là bất khả thi theo thiết kế |
| Error rate `/ask` | < 2 % | Mock giả lập lỗi upstream 1% (`MOCK_ERROR_RATE=0.01`). Đo được 0.67–1.33%. Ngưỡng 2% chừa biên cho dao động mà vẫn bắt được khi lỗi tăng gấp đôi |
| Accuracy trên golden dataset | ≥ 85 % | Bằng ngưỡng quality gate trong CI (`.github/workflows/eval.yml`). Thấp hơn 100% vì eval chấm theo keyword nên có thể đánh trượt câu đúng nhưng diễn đạt khác. Kèm điều kiện **không regression** so với bản trước |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Lệnh: `python load_test.py --url http://localhost:8002 --requests 300 --concurrency <c> --out reports/load_v2_c<c>.json` (`MOCK_SLOW_RATE` mặc định 0.03).

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.85 | 202.3 | 247.4 | 1721.1 | 1.00% (3×503) | ✅ PASS |
| 10 | 35.69 | 189.1 | 470.3 | 1680.5 | 1.33% (4×503) | ✅ PASS |
| 50 | 95.82 | 208.5 | 558.8 | 1723.5 | 1.00% (3×503) | ❌ FAIL (p95) |
| 100 | 41.25 | 986.7 | 4678.4 | 5165.3 | 1.00% (3×503) | ❌ FAIL (p95) |

Chạy lại để kiểm tra (file `reports/load_v2_c100_recheck.json`, `reports/load_v2_c75_recheck.json`): c=100 được 53.86 RPS, p50 718.0, p95 4419.5 ms. c=75 được 48.68 RPS, p50 582.9, p95 3605.7 ms.

**Nhận xét:** RPS **chỉ tăng gần tuyến tính ở tải thấp**.
- **1 → 10:** RPS tăng 9.3 lần (3.85 → 35.69), p50 gần như không đổi. Thời gian của mỗi request chủ yếu là **chờ I/O** (mock LLM dùng `asyncio.sleep`), event loop xử lý song song được. Theo định luật Little, RPS ≈ concurrency / latency ≈ 10 / 0.24 s ≈ 41, khớp với số đo.
- **10 → 50:** RPS chỉ tăng 2.7 lần (lẽ ra khoảng 200 nếu tuyến tính), còn p95 vượt SLO (558.8 ms). Agent chỉ có **1 process**, mọi request dùng chung 1 event loop và 1 CPU core cho phần việc tốn CPU (parse JSON, pydantic, ghi log JSON, cập nhật metrics). Client `load_test.py` cũng giành CPU trên cùng máy. Request bắt đầu phải xếp hàng.
- **50 → 100:** hệ thống **quá tải và sập throughput**: RPS giảm (95.82 → 41.25), p50 tăng gần 5 lần, p95 lên 4.7 s. Hai lần chạy kiểm tra cho kết quả tương tự, nên không phải nhiễu. Latency nhảy theo bậc khoảng 3 s (p90 khoảng 3.8 s, max 6.7 s) trong khi CPU của agent thấp. Giả thuyết của mình là khi 100 kết nối mở cùng lúc, một phần gói mở kết nối TCP (SYN) trên Windows bị chờ timeout khoảng 3 s rồi mới gửi lại, tức nút thắt nằm ở lớp kết nối chứ không ở LLM.
- **Kết luận:** một instance này chịu được khoảng **10–50 request đồng thời** trong SLO. Muốn hơn thì phải scale ngang (nhiều worker / instance sau load balancer, xem mục 5), không thể chỉ tăng concurrency.

### 2.2 Tail latency

Lệnh: khởi động lại v2 với `MOCK_SLOW_RATE=<x>`, chạy `python load_test.py --url http://localhost:8002 --requests 300 --concurrency 20 --out reports/load_v2_slow_<x>.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 206.0 | 450.4 | 482.7 |
| 0.03 (mặc định) | 258.6 | 493.0 | 1693.8 |
| 0.1 | 382.1 | 1695.4 | 1737.3 |

(p50 gần như không đổi: 190.3 / 190.7 / 188.2 ms. RPS giảm 94.37 → 58.3 → 42.74.)

**Nhận xét:**
- **Chỉ số nhạy nhất là p99.** Chỉ cần 3% request chậm thì p99 tăng 3.5 lần (482.7 → 1693.8 ms), trong khi avg chỉ tăng 25% (206.0 → 258.6) và p50 không đổi. p95 vẫn dưới 500 ms vì 3% < 5%: request chậm nằm hết trong 5% đuôi mà p95 bỏ qua. Lên 10% request chậm (> 5%) thì p95 mới vọt lên 1695.4 ms.
- **Vì sao avg chỉ tăng nhẹ:** avg chia đều 1.5 s chậm thêm cho cả 300 request (khoảng 0.03 × 1500 ≈ +45 ms, đo được +52.6 ms), nên trông vẫn "ổn". Thực tế 3% người dùng phải chờ khoảng 1.7 s.
- **Vì sao SLO không nên đặt theo average:**
  - Avg là trung bình của cả phần nhanh lẫn phần chậm, nên bị phần đông request nhanh kéo xuống và **che mất trải nghiệm của nhóm user tệ nhất**.
  - SLO theo p95/p99 thể hiện cam kết "95% / 99% request nhanh hơn X ms", tức đo đúng trải nghiệm người dùng.
  - Một trang gọi agent nhiều lần thì gần như chắc chắn sẽ gặp request ở đuôi.
- RPS cũng giảm theo tỉ lệ request chậm. Concurrency cố định 20 nên request chậm giữ chỗ lâu hơn, đúng theo định luật Little.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Lệnh:
```bash
python eval/run_eval.py --url http://localhost:8001 --out reports/eval_v1.json
python eval/run_eval.py --url http://localhost:8002 --out reports/eval_v2.json --baseline reports/eval_v1.json
# sửa KNOWLEDGE_BASE, khởi động lại v2
python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json
```

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.3% (21/23) | **100% (23/23)** |
| Avg tokens / câu | 57.5 | 108.7 | 115.7 |
| Tổng cost (USD) | 0.000410 | 0.000756 | 0.000808 |
| Cost / câu đúng (USD) | 0.00040995 | 0.00003599 | 0.00003511 |
| Latency p50 / p95 (ms) | 168.5 / 204.2 | 202.0 / 1579.5 | 213.9 / 233.3 |
| Quality gate | ❌ FAIL (gate 80%) | ✅ PASS (gate 80%, 0 regression so với v1) | ✅ PASS (gate 100%, 0 regression so với v2) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` ("JWT khác gì API key trong xác thực?") | `token`, `hết hạn`, `chữ ký` | KB không có tài liệu nào chứa từ khoá của câu hỏi, nên retrieval rỗng và agent trả câu chung chung. Thêm tài liệu kích hoạt bởi `["jwt", "api key"]`: API key là chuỗi bí mật cố định, còn JWT là **token** có **chữ ký** số, mang thông tin user và thời điểm **hết hạn** (`exp`), server chỉ kiểm tra chữ ký |
| `scaling-03` ("Kubernetes HPA scale dựa trên những chỉ số nào?") | `cpu`, `memory`, `custom metrics` | Cùng nguyên nhân. Thêm tài liệu kích hoạt bởi `["kubernetes", "hpa", "autoscal"]`: HPA tăng giảm số pod theo **CPU**, **memory** hoặc **custom metrics** (RPS, độ dài hàng đợi) |

Sửa trong `06-lab-complete/benchmark-observability/develop/utils/mock_llm.py`, và chép cùng 2 tài liệu sang `production/utils/mock_llm.py` để stack Docker ở mục 4 cũng đạt 100%. Không sửa `golden_dataset.jsonl`. Kiểm tra không regression:
- Từ khoá mới không xuất hiện trong 21 câu hỏi còn lại của golden dataset, nên không câu nào đổi tài liệu được retrieve.
- Lần eval cuối báo `Câu bị regression : 0`.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- **Chất lượng:** retrieval (RAG) đưa accuracy từ 4.35% lên 91.3%. v1 chỉ biết vài câu chung chung nên gần như không dùng được.
- **Chi phí mỗi câu tăng:** v2 nhét tài liệu vào prompt nên số token tăng 1.9 lần (57.5 → 108.7) và tổng cost tăng 1.84 lần.
- **Chi phí mỗi câu đúng giảm mạnh:** cost / câu đúng của v2 **rẻ hơn khoảng 11.4 lần** (0.00040995 → 0.00003599 USD), vì v1 tốn tiền cho 22 câu sai. Đó là lý do nên so phiên bản bằng "cost / câu đúng" thay vì "cost / câu".
- **Latency:** v2 chậm hơn khoảng 30–45 ms ở p50 (168.5 → 202.0 / 213.9), do bước retrieval khoảng 20 ms và prompt dài hơn (mock cộng 0.2 ms/token). p95 1579.5 ms của lần eval v2 đầu tiên là do 1 trong 23 request dính tail latency (3% request chậm). Với mẫu chỉ 23 câu, p95 rất dễ bị một request kéo lệch, nên latency phải đo bằng load test (mục 2), không lấy từ eval.
- **Sửa KB** tăng thêm 7 token / câu (+7% cost) nhưng đưa accuracy lên 100%, nên cost / câu đúng còn giảm tiếp (0.00003599 → 0.00003511).

**Quality gate trong CI** (Exercise 7.3): [`.github/workflows/eval.yml`](.github/workflows/eval.yml).
- Workflow chạy mỗi khi có pull request sửa vào `develop/`: bật agent v2 (`MOCK_ERROR_RATE=0` để gate không fail ngẫu nhiên), chờ `/health`, rồi chạy `python eval/run_eval.py --min-accuracy 0.85`.
- `run_eval.py` gọi `SystemExit(1)` khi accuracy < ngưỡng hoặc có regression so với `--baseline`. Exit code ≠ 0 làm step fail, kéo theo job fail.
- Bật **branch protection** trên `main`, đặt check `quality-gate / eval` là **required**, thì PR không merge được khi gate fail.
- Đã thử: chạy gate với agent v1 (`--url http://localhost:8001 --min-accuracy 0.85`) → `Quality gate (accuracy ≥ 85%, không regression): ❌ FAIL`, `exit=1`.

### Phụ lục — Exercise 7.1: đọc metrics của agent

Sau 1 request `POST /ask` với câu "Prometheus thu thập metrics như thế nào?" (output `GET /metrics` của v2, đã lọc bớt):

```text
http_requests_total{method="POST",route="/ask",status="200"} 1.0
http_request_duration_seconds_count{method="POST",route="/ask"} 2.0
http_request_duration_seconds_sum{method="POST",route="/ask"} 0.2329173999996783
agent_in_flight_requests 0.0
llm_requests_total{model="mock-llm-small",status="ok"} 1.0
llm_tokens_total{model="mock-llm-small",type="input"} 91.0
llm_tokens_total{model="mock-llm-small",type="output"} 55.0
llm_cost_usd_total{model="mock-llm-small"} 4.6649999999999996e-05
agent_question_length_chars_bucket{le="50.0"} 1.0
agent_question_length_chars_count 1.0
agent_question_length_chars_sum 40.0
agent_info{model="mock-llm-small",version="v2"} 1.0
```

1. **Mỗi loại metric một ví dụ:**
   - **Counter**, chỉ tăng: `http_requests_total{method="POST",route="/ask",status="200"}`, `llm_tokens_total`, `llm_cost_usd_total`.
   - **Gauge**, lên xuống được: `agent_in_flight_requests` (số request đang xử lý), `agent_info` (luôn = 1, mang label version/model).
   - **Histogram**: `http_request_duration_seconds` (gồm các series `_bucket{le=...}`, `_count`, `_sum`, dùng `histogram_quantile` để tính p95).
2. **Nếu dùng `request.url.path` làm label `route`:** mỗi URL lạ mà bot quét (`/wp-admin`, `/.env`, `/a1b2c3`…) tạo ra một **time series mới** cho `http_requests_total`, và **14 series** cho histogram latency (11 bucket + `+Inf`, cộng `_count`, `_sum`), nhân thêm với method/status. Bot quét hàng nghìn URL thì sinh ra hàng chục nghìn series. Đó là **cardinality explosion**: Prometheus tốn RAM và disk tỉ lệ với số series, query và dashboard chậm, có thể OOM. Kẻ tấn công còn có thể cố ý làm sập hệ thống giám sát. Dùng route template (`/ask`) và gom URL không khớp vào `unmatched` thì số series luôn có giới hạn.
3. **Metric mới `agent_question_length_chars`** (đã thêm vào `develop/app.py`): một Histogram với bucket `10, 20, 50, 100, 200, 500, 1000, 2000`, gọi `QUESTION_LENGTH.observe(len(body.question))` ở đầu `/ask`. Câu hỏi 40 ký tự ở trên rơi vào bucket `le="50.0"`, `_sum` = 40. Dùng Histogram chứ không dùng label `length=...` vì độ dài có vô số giá trị, làm label sẽ gây cardinality bùng nổ đúng như câu 2.

---

## 4. Observability stack (production)

Stack chạy bằng `docker compose -p k5-day14-observability up -d --build` trong `06-lab-complete/benchmark-observability/production/`: agent ×2 (mỗi container giới hạn 0.5 CPU / 256 MB) + Nginx + Prometheus + Grafana + Jaeger + Locust. Unit test alert rules bằng `promtool test rules /p/alert_rules_test.yml` cho kết quả `SUCCESS`.

> Sửa 1 lỗi của Dockerfile mẫu: agent crash vòng lặp với `ModuleNotFoundError: No module named 'uvicorn'`. Nguyên nhân là `useradd -d /app` đặt HOME của user `agent` là `/app`, nên Python tìm package `--user` ở `/app/.local`, trong khi package được copy vào `/home/agent/.local`. Đã thêm `ENV PYTHONUSERBASE=/home/agent/.local` (giống Dockerfile Part 5).

### Exercise 7.4 — đọc dashboard khi có tải

Locust headless **30 users, ramp 5/s** (`docker compose run -d --no-deps locust ... -u 30 -r 5`). Số đọc từ Prometheus lúc 16:50:27, cửa sổ `rate(...[1m])`, 2 instance:

| Chỉ số | Giá trị |
|---|---|
| Traffic `/ask` | 18.77 req/s |
| Error rate | 1.65% |
| p50 / **p95** / p99 | 174.8 / **295.2** / 1856.7 ms |
| **avg** | **240.8 ms** |
| Req/s theo instance | `172.21.0.6`: 9.51 · `172.21.0.8`: 9.26 |
| Tokens/s | input 1443.25 · output 761.31 |
| `curl -i http://localhost:8080/metrics` | `HTTP/1.1 404 Not Found` (`Server: nginx/1.28.3`) |

1. **p95 và avg:** p95 = 295.2 ms, avg = 240.8 ms, p95 chỉ cao hơn avg khoảng 1.2 lần. Vậy 95% request có latency khá đồng đều quanh p50 (175 ms, gần bằng latency của mock LLM). Nhưng p99 = 1856.7 ms, gấp khoảng 7.7 lần avg. Khoảng 3% request (`MOCK_SLOW_RATE=0.03`) chậm thêm khoảng 1.5 s, và avg không cho thấy điều này. Khoảng cách giữa avg và p99 chính là **tail latency**.
2. **Nginx có chia đều không:** có. 9.51 và 9.26 req/s (lệch khoảng 1.4%), đúng kiểu round-robin của `upstream agent_cluster`. Header `X-Served-By` khi gọi `/health` 6 lần cũng chia đều 2/2/2 cho 3 IP lúc scale 3.
3. **Input tokens/s > output tokens/s** (1443 so với 761, khoảng 1.9 lần): prompt gửi LLM gồm system prompt, **tài liệu retrieve được** và câu hỏi, còn câu trả lời của mock chỉ là 1 tài liệu. Agent v2 dùng RAG nên input luôn dài hơn output. Ở LLM thật, giá output đắt hơn khoảng 4 lần giá input nên vẫn phải theo dõi cả hai.
4. **`/metrics` qua Nginx trả 404** vì `nginx.conf` có `location = /metrics { return 404; }`. Prometheus scrape thẳng `agent:8000/metrics` trong network nội bộ `obs_net`, không đi qua Nginx. Metrics lộ route, lưu lượng, version, model, chi phí, nên không public ra Internet.

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [`screenshots/grafana-dashboard.png`](screenshots/grafana-dashboard.png). Cửa sổ 20 phút gồm 2 đợt 100 user (benchmark scale), tải nền 30 user và 5 thí nghiệm ở 4.2
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với **2 alert cùng firing** (`LLMCostBurnRateHigh` + `AgentHighErrorRate`): [`screenshots/prometheus-alert-firing.png`](screenshots/prometheus-alert-firing.png)

### 4.2 Thí nghiệm "phá hệ thống"

Cách làm:
- Locust chạy nền 30 user trong suốt bài.
- Mỗi thí nghiệm sửa `.env` rồi chạy `docker compose -p k5-day14-observability up -d agent` (tạo lại 2 container agent).
- Mốc "lúc đổi" là khi lệnh `up` xong, hoặc ngay sau `docker pause`.
- Script hỏi `GET /api/v1/alerts` của Prometheus mỗi 2 s và ghi lại lúc alert chuyển `pending` rồi `firing`.
- Sau mỗi thí nghiệm trả `.env` về như `.env.example` (D thì `docker unpause`).

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (error rate đo được 20.75%) | pending sau 24 s → **firing sau 84 s** (`for: 1m`) | **Error rate** chuyển đỏ. *LLM calls theo kết quả* có đường `error` tăng. *Requests/s theo status code* có thêm 503 |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (p95 1913.5 ms, p99 1982.7 ms, avg 622.2 ms, p50 199.0 ms) | pending sau 20 s → **firing sau 141 s** (`for: 2m`) | **Latency /ask — p50/p95/p99**: p95 vượt vạch đỏ 1 s, p50 không đổi. *LLM latency p95* lên khoảng 1.9 s cho thấy nguyên nhân ở LLM |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (cost 1.90 → 16.84 $/giờ lúc firing, 18.30 $/giờ khoảng 3 phút sau) | pending sau 22 s → **firing sau 143 s** (`for: 2m`) | **Cost burn rate (USD/giờ)** vọt lên khoảng $18. *LLM latency p95 theo model* xuất hiện series `mock-llm-large` (p50 /ask 199 → 412 ms, khoảng 2 lần) |
| D | `docker pause k5-day14-observability-agent-1` | `AgentInstanceDown` (`instance=172.21.0.8:8000`) | pending sau 2 s → **firing sau 42 s** (`for: 30s` + chu kỳ scrape 5 s) | **Instances up** 2 → 1. *Requests/s theo instance* dồn hết về 1 instance (13.11 req/s). Error rate của agent vẫn **xanh** (0.83%) nhưng max latency phía Locust lên **10002 ms**: request bị Nginx giữ tới hết `proxy_read_timeout 10s` rồi trả 504, metric của agent không thấy |
| E | `AGENT_VERSION=v1` | **Không có** (chờ 150 s: `AgentHighErrorRate` không firing, error rate 1.05%, p95 198.4 ms) | — | *Retrieval hit ratio* mất dữ liệu (trước đó 17.95 hit/s). *Tokens/s* giảm một nửa (input 1391 → 688, output 730 → 375). Bảng **Phiên bản đang chạy** đổi `v2` → `v1` |

**Quan sát thêm:**
- **`LLMCostBurnRateHigh` firing ngay cả khi chưa phá gì.** Alert bật từ 09:45:32 UTC, lúc chạy benchmark 100 user, và vẫn firing sau khi chuyển về 30 user với model nhỏ. Lúc 16:50:27 đo được 4.80 $/giờ, nhưng cửa sổ 5 phút vẫn còn lẫn đợt 100 user. Ước tính riêng cho 30 user: 18.77 req/s × khoảng 4.7e-5 USD/request (theo `cost_usd` trong log) × 3600 ≈ 3.2 $/giờ, vẫn > ngưỡng 2 $/giờ. Ngưỡng tuyệt đối tính theo giờ phụ thuộc vào traffic: nhiều user hơn là "đốt tiền" nhiều hơn dù không có sự cố. Nên đổi sang **cost / request** hoặc so với budget ngày.
- **B làm alert cost tự hết.** Request chậm hơn mà số user cố định thì RPS giảm (18.8 → 15.1 req/s), nên cost/giờ rơi xuống 1.90 $/giờ, dưới ngưỡng. Nhờ vậy C mới đo được thời gian tới firing từ trạng thái inactive.
- **Thời gian tới firing ≈ thời gian `for` + 20–25 s.** Khoảng 20–25 s là lúc `rate(...[1m])` (hoặc `[5m]`) tích luỹ đủ dữ liệu mới để vượt ngưỡng (pending), cộng chu kỳ scrape/evaluation 5 s. Riêng D gần như tức thì vì `up == 0` đúng ngay từ lần scrape đầu tiên thất bại.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Đây là **lỗi chất lượng**: hệ thống vẫn khoẻ (thậm chí nhanh hơn, rẻ hơn) nhưng trả lời sai (accuracy v1 chỉ 4.35% so với 100%, mục 3). Metric hạ tầng không thể thấy. Các cách phát hiện:
1. **Chặn trước khi deploy:** quality gate chạy eval golden dataset trong CI/CD (`.github/workflows/eval.yml`, `--min-accuracy` + `--baseline` để bắt regression). Bản v1 không qua được gate (đã thử ở mục 3: exit 1).
2. **Canary + eval online:** khi deploy, chỉ cho 5–10% traffic vào bản mới. Lấy mẫu câu hỏi/câu trả lời thật để chấm bằng LLM-as-judge hoặc so keyword định kỳ, rồi so với bản cũ trước khi tăng traffic.
3. **Alert trên metric "đại diện" cho chất lượng:**
   - Retrieval hit ratio giảm, ví dụ `rate(agent_retrieval_total{result="hit"}[5m]) / rate(http_requests_total{route="/ask"}[5m]) < 0.8`.
   - Tokens trung bình mỗi request giảm đột ngột.
   - `agent_info` đổi version ngoài lịch deploy.
4. **Tín hiệu từ người dùng:** tỉ lệ 👍/👎, tỉ lệ hỏi lại hoặc diễn đạt lại câu hỏi, tỉ lệ chuyển sang người hỗ trợ.

### 4.3 Debug bằng trace

Trace chậm nhất (Jaeger, service `observable-agent`, `POST /ask`, lọc `minDuration=1500ms` có 509 trace, sắp xếp giảm dần): [`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png)

- `trace_id`: `d514d54ba9fbe007615ed70b17a3c0d3`
- Tổng thời gian: **1946.2 ms** (`POST /ask`, HTTP 200)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**1661.3 ms, 85.4%**, `gen_ai.request.model=mock-llm-small`, `gen_ai.usage.input_tokens=81`, `output_tokens=46`)
- Các span khác:
  - `agent.run` 1756.0 ms (90.2%).
  - `agent.retrieve_context` 94.6 ms (4.9%), trong khi bình thường khoảng 20 ms.
  - Phần nằm ngoài `agent.run` khoảng 190 ms.
- Kết luận: tail latency chủ yếu do **LLM upstream** (request rơi vào nhóm "slow" +1.5 s của mock), không phải do code của agent. Trace này xảy ra lúc 16:44:54, trong benchmark **100 user với 1 instance giới hạn 0.5 CPU**. Retrieval chậm gấp 4–5 lần bình thường và khoảng 190 ms chờ ngoài `agent.run` là dấu hiệu instance bị **tranh CPU / xếp hàng event loop** dưới tải.
- Dòng log tương ứng (`docker compose -p k5-day14-observability logs agent | grep d514d54ba9fbe007615ed70b17a3c0d3`):

```json
{"ts": "2026-11-26T09:44:56.174002+00:00", "level": "INFO", "service": "observable-agent", "instance": "bffdfc7fb9fd", "event": "llm_call", "trace_id": "d514d54ba9fbe007615ed70b17a3c0d3", "span_id": "ea9916d2e11ccb91", "request_id": "a0eae846d1e0", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 81, "output_tokens": 46, "cost_usd": 4e-05, "llm_ms": 1662.2}
{"ts": "2026-11-26T09:44:56.174523+00:00", "level": "INFO", "service": "observable-agent", "instance": "bffdfc7fb9fd", "event": "http_request", "trace_id": "d514d54ba9fbe007615ed70b17a3c0d3", "span_id": "ea9916d2e11ccb91", "request_id": "a0eae846d1e0", "method": "POST", "route": "/ask", "status": 200, "ms": 1945.6}
```

`llm_ms: 1662.2` trong log khớp với span `chat mock-llm-small` 1661.3 ms. `ms: 1945.6` khớp với tổng 1946.2 ms của trace.

**Trace lỗi** ([`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png)):
- `trace_id` `72e29ae857eed899e249184a30ae4674`, 94.2 ms, `POST /ask` trả **503**.
- Span `chat mock-llm-small` (72.7 ms) có `status=ERROR`, `error.type=upstream_unavailable` và **event `exception`**: `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)`. Lỗi được ghi lại ở cả `agent.run`.
- Lỗi trả về nhanh (94 ms so với khoảng 190 ms của request thành công) vì mock giả lập lỗi upstream đến sớm.
- Log cùng `trace_id`:

```json
{"ts": "2026-11-26T09:50:59.627713+00:00", "level": "INFO", "service": "observable-agent", "instance": "bffdfc7fb9fd", "event": "llm_error", "trace_id": "72e29ae857eed899e249184a30ae4674", "span_id": "6ad994f54456b2f3", "request_id": "c184d433316a", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-26T09:50:59.627983+00:00", "level": "INFO", "service": "observable-agent", "instance": "bffdfc7fb9fd", "event": "http_request", "trace_id": "72e29ae857eed899e249184a30ae4674", "span_id": "6ad994f54456b2f3", "request_id": "c184d433316a", "method": "POST", "route": "/ask", "status": 503, "ms": 93.7}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Lệnh (thêm `--no-deps` để `compose run` không tự bật lại agent theo `replicas: 2`, và `MSYS_NO_PATHCONV=1` vì chạy từ Git Bash trên Windows):

```bash
docker compose -p k5-day14-observability up -d --scale agent=1
docker compose -p k5-day14-observability run --rm --no-deps locust -f /mnt/locust/locustfile.py --host http://nginx \
  --headless -u 100 -r 10 -t 2m --csv /mnt/results/scale_1
docker compose -p k5-day14-observability up -d --scale agent=3      # chờ Prometheus thấy 3 target "up"
docker compose -p k5-day14-observability run --rm --no-deps locust ... --csv /mnt/results/scale_3
```

Số liệu dòng `POST /ask` trong [`benchmark-results/scale_1_stats.csv`](benchmark-results/scale_1_stats.csv) và [`benchmark-results/scale_3_stats.csv`](benchmark-results/scale_3_stats.csv):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 60.07 | 190 | 290 | 1700 | 74 / 7178 (1.03%, toàn bộ 503 của mock LLM) |
| 3 | 60.00 | 190 | **220** | 1700 | 72 / 7167 (1.00%, toàn bộ 503 của mock LLM) |

(Dòng Aggregated, gồm cả `/health`: 65.73 và 65.95 req/s. avg `/ask` 241.4 và 238.3 ms. max 1954.6 và 1735.8 ms.)

**Giải thích kết quả:**
- **RPS không đổi (khoảng 60 req/s)** vì Locust là **closed-loop**: 100 user, mỗi user chờ phản hồi rồi nghỉ 0.5–2 s (trung bình 1.25 s). Tải tối đa họ tạo ra khoảng 100 / (1.25 + 0.24) ≈ 67 req/s, khớp với 65.7–66.0 req/s đo được. 1 instance đã phục vụ hết tải này (error rate ~1% chỉ là lỗi giả lập), nên thêm instance không tăng throughput: nút thắt nằm ở số user tạo tải.
- **p95 có cải thiện: 290 → 220 ms (−24%).** Với 1 instance giới hạn 0.5 CPU phải nhận khoảng 60 req/s, phần việc tốn CPU (parse JSON, pydantic, log, metrics, tracing) bắt đầu xếp hàng trên event loop. Trace chậm ở 4.3 (chụp đúng lúc chạy `scale_1`) cho thấy điều đó: khoảng 190 ms chờ ngoài `agent.run` và retrieval chậm 4–5 lần. Chia ra 3 instance (khoảng 20 req/s mỗi cái) thì hết xếp hàng.
- **p50 (190 ms) và p99 (1700 ms) không đổi.** Đó là latency của **LLM upstream**: p50 gần như bằng `MOCK_LATENCY_MS` + jitter, còn p99 là 3% request "slow" bị cộng thêm 1.5 s. Panel *LLM latency p95* không đổi giữa 2 lần chạy. Scale ngang agent **không sửa được latency của LLM**. Muốn giảm tail phải xử lý phía LLM: timeout + retry/hedging, cache câu trả lời, streaming, model nhỏ hơn hoặc nhà cung cấp khác.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Đặt SLO theo percentile chứ không theo average.** 3% request chậm làm p99 tăng 3.5 lần nhưng avg chỉ tăng 25% (mục 2.2). Avg không thấy được trải nghiệm của nhóm user tệ nhất.
  2. **Throughput có điểm gãy, và scale chỉ chữa được đúng nút thắt.** Một process async quá khoảng 50 request đồng thời thì xếp hàng rồi sập (mục 2.1). Scale 1 → 3 instance cải thiện p95 (290 → 220 ms) vì bớt tranh CPU, nhưng không chạm được p50/p99 do LLM upstream quyết định (mục 5). Phải nhìn trace để biết thời gian nằm ở span nào trước khi quyết định scale.
  3. **Metric hạ tầng không thấy lỗi chất lượng, và alert phải được thiết kế theo ngữ cảnh.** Đổi sang v1 (accuracy 4.35%) không làm alert nào kêu, chỉ eval và quality gate bắt được (mục 3, 4.2-E). Alert cost theo ngưỡng tuyệt đối thì firing ngay ở traffic bình thường. Còn `docker pause` tạo lỗi 504 ở Nginx mà dashboard của agent vẫn xanh.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - **Giám sát ở tầng Nginx/LB và synthetic check từ bên ngoài:** tỉ lệ 5xx/504 và latency do Nginx ghi (thí nghiệm D cho thấy metric của agent bỏ sót). Thêm uptime check gọi `/ask` từ ngoài Internet.
  - **Alert SLO theo error budget burn rate**, cửa sổ đa mức (ví dụ 5 phút / 1 giờ, burn rate > 14.4), thay cho ngưỡng tức thời. Ít báo động giả hơn và báo sớm khi sắp hết budget tháng.
  - **Cost:** alert theo **cost / request** và **% budget ngày đã dùng** (ví dụ > 80%) thay cho USD/giờ tuyệt đối. Thêm metric cost theo user/API key (label có giới hạn, ví dụ tier) để bắt một khách hàng đốt tiền.
  - **Chất lượng:**
    - Retrieval hit ratio và tokens/request có alert khi giảm đột ngột.
    - Tỉ lệ câu trả lời rỗng hoặc "không biết".
    - Điểm eval online (LLM-as-judge trên mẫu traffic) và feedback 👍/👎 của user.
    - Annotation trên Grafana mỗi lần deploy, để nối sự thay đổi chất lượng với version.
  - **LLM upstream:**
    - Tỉ lệ lỗi và latency theo provider/model.
    - Số lần retry, số request bị rate limit (429) từ provider.
    - Time-to-first-token nếu dùng streaming.
  - **Saturation:** CPU/memory của container (cAdvisor), độ dài hàng đợi hoặc in-flight theo instance. Alert khi CPU gần giới hạn 0.5 core, vì mục 5 cho thấy đó là nút thắt đầu tiên của agent khi tải tăng.
