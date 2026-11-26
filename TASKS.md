# Danh sách công việc — Day 14

> Deadline: **23h59 (GMT+7) ngày lab**. Đạt: 70/100 (84/120 điểm thô).
> Chi tiết từng bước: [CHECKPOINTS.md](CHECKPOINTS.md) · Đề bài: [CODE_LAB.md](CODE_LAB.md) · Điểm: [RUBRIC.md](RUBRIC.md)

## CP0 — Setup (10')
- [x] Kiểm tra `python --version` (3.11+), `docker compose version`, `docker run --rm hello-world`
- [x] Windows: chạy Python trong WSL2 (`python -c "import os; print(os.name)"` → `posix`)
- [x] Tạo file `MISSION_ANSWERS.md` ở gốc repo

**Mục đích:** máy chạy được Python và Docker. Có WSL2 thì script chấm mới gửi được SIGTERM để đạt 12/12.

## CP1 — Part 1: Localhost vs Production (20' · 8 điểm)
- [x] Đọc `01-localhost-vs-production/develop/app.py`, tìm ≥ 5 anti-pattern
- [x] Chạy bản develop: `curl -X POST "http://localhost:8000/ask?question=Hello"`
- [x] Lập bảng so sánh develop và production, có cột giải thích

**Mục đích:** hiểu vì sao code chạy trên laptop chưa dùng được cho production (hardcode secret, thiếu health check, thiếu graceful shutdown…).

## CP2 — Part 2: Docker (30' · 8 điểm)
- [x] Trả lời 4 câu của Exercise 2.1
- [x] Build image **từ gốc repo** (`docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .` và bản `production`)
- [x] Đo kích thước bằng `docker images`, tính % chênh lệch
- [x] `touch 02-docker/production/.env.local`, chạy stack compose, test qua Nginx, vẽ sơ đồ các service

**Mục đích:** đóng gói agent để chạy giống nhau ở mọi máy, thấy multi-stage build và thứ tự layer giúp giảm dung lượng và tăng tốc build.

## CP3 — Part 4: API Security (25' · 8 điểm)
- [x] Bản develop: `AGENT_API_KEY=secret-key-123 python app.py`, thử có key và không có key
- [x] Bản production: lấy token ở `POST /auth/token` (`student` / `demo123`)
- [x] Vòng lặp curl để thấy 429, dán output `curl -i` cho 401 / 200 / 429 (che token)
- [x] Giải thích cách hoạt động của cost guard

**Mục đích:** chặn truy cập trái phép (auth), chặn gọi quá nhanh (rate limit) và chặn tiêu quá ngân sách (cost guard).

## CP4 — Part 5: Scaling & Reliability (20' · 8 điểm)
- [x] Trả lời Exercise 5.1–5.3 (health/ready, graceful shutdown, stateless)
- [x] `touch 05-scaling-reliability/production/.env.local`
- [x] `docker compose -p k5-day14-scaling up -d --build --scale agent=3`
- [x] `python test_stateless.py` rồi giải thích kết quả
- [x] `docker compose -p k5-day14-scaling down`

**Mục đích:** chạy nhiều instance mà không mất state (state nằm trong Redis), phân biệt liveness với readiness.

## CP5 — Part 6: Final Project (60' · **60 điểm**)
Sửa các chỗ `TODO` trong `06-lab-complete/` theo thứ tự trong [06-lab-complete/README.md](06-lab-complete/README.md):
- [x] `app/config.py`: đọc toàn bộ cấu hình từ biến môi trường
- [x] `app/redis_client.py`: kết nối Redis
- [x] `app/auth.py`: kiểm tra `X-API-Key`, thiếu hoặc sai trả 401
- [x] `app/rate_limiter.py`: vượt giới hạn trả 429, state lưu trong Redis
- [x] `app/cost_guard.py`: vượt ngân sách trả 402
- [x] `app/main.py`: `/ask`, `/health` (200 kể cả khi Redis chết), `/ready` (503 khi mất Redis), xử lý lỗi, SIGTERM
- [x] `Dockerfile` (multi-stage, < 500 MB), `.dockerignore`, `docker-compose.yml` (agent + Redis)
- [x] `.env.example`, `railway.toml` / `render.yaml`
- [x] `python check_production_ready.py --static-only` sau mỗi bước, rồi chạy bản đầy đủ tới khi **PASS 12/12**
- [x] Dán phần "📋 Checklist Deliverable" vào `MISSION_ANSWERS.md`

**Mục đích:** ráp mọi kỹ thuật ở trên thành một agent production đạt đủ 12 tiêu chí. Đây là phần nhiều điểm nhất.

## CP6 — Part 3: Cloud Deployment (25' · 8 điểm + 10 điểm của Part 6)
- [x] Deploy `06-lab-complete/` lên Railway (`cd 06-lab-complete && railway up`) hoặc Render
- [x] Tạo Redis trên cloud, đặt `REDIS_URL` và `AGENT_API_KEY` bằng biến môi trường trên nền tảng
- [x] Chạy 4 lệnh tự kiểm ở CP6: `/health` 200, `/ready` 200, `/ask` không key 401, có key 200
- [x] Viết `DEPLOYMENT.md`, chụp `dashboard.png`, `running.png`, `test.png` vào `screenshots/`
- [x] Trong `MISSION_ANSWERS.md`: ghi URL, so sánh `railway.toml` với `render.yaml`, viết 3–5 dòng về pipeline Cloud Run

**Mục đích:** đưa agent lên một URL public chạy thật, giữ secret ngoài code.

## CP7 — Part 7 Bước 1: Benchmark local (45' · 9 điểm)
- [x] Chạy agent v1 (cổng 8001) và v2 (cổng 8002)
- [x] `cp -n 06-lab-complete/benchmark-observability/BENCHMARK_REPORT_TEMPLATE.md BENCHMARK_REPORT.md`
- [x] Load test với concurrency 1/10/50/100, lưu `reports/load_v2_c*.json`
- [x] So sánh `MOCK_SLOW_RATE` = 0 / 0.03 / 0.1, lưu `reports/load_v2_slow_*.json`
- [x] Eval v1 và v2, lưu `reports/eval_v1.json`, `reports/eval_v2.json`
- [x] Sửa `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py`, khởi động lại v2, eval lại đạt 23/23 và lưu `reports/eval_v2_fixed.json`
- [x] Viết job CI hoặc giải thích cách dùng exit code của `run_eval.py` để chặn merge

**Mục đích:** đo bằng số của chính mình xem agent nhanh tới đâu (p50/p95/p99, RPS) và đúng tới đâu (accuracy), rồi dùng quality gate để chặn bản kém hơn.

## CP8 — Part 7 Bước 2: Observability (sau giờ lab · 11 điểm)
- [x] `docker compose -p k5-day14-observability up -d --build --scale agent=1`
- [x] Chạy Locust headless với scale 1 và scale 3, lưu `scale_1_stats.csv` và `scale_3_stats.csv`
- [x] Chụp `grafana-dashboard.png` khi đang có tải, trả lời Exercise 7.4
- [x] Jaeger: chụp `jaeger-slow-trace.png`, `jaeger-error-trace.png`, chép dòng log JSON có cùng `trace_id`
- [x] Làm cho ≥ 2 alert firing, ghi thời gian tới lúc firing, chụp `prometheus-alert-firing.png`
- [x] Điền đủ `BENCHMARK_REPORT.md`
- [x] `docker compose -p k5-day14-observability down -v` (chỉ sau khi đã chụp đủ ảnh)

**Mục đích:** nhìn được sức khoẻ của agent khi đang chạy (metrics, trace, alert) và phát hiện sự cố trước khi người dùng thấy.

## Đóng gói và nộp
- [ ] Copy kết quả ra gốc repo:
  ```bash
  mkdir -p reports benchmark-results
  cp -r 06-lab-complete/benchmark-observability/develop/reports/. reports/
  cp -r 06-lab-complete/benchmark-observability/production/benchmark-results/. benchmark-results/
  ```
- [ ] Có đủ 7 ảnh trong `screenshots/`
- [ ] Số trong `BENCHMARK_REPORT.md` khớp với file JSON/CSV
- [ ] Ghi đủ mục **AI log** cuối `MISSION_ANSWERS.md`
- [ ] Không có `.env` hay secret trong lịch sử commit: `git log --all --oneline -- '*.env' '.env'` không in gì
- [ ] Repo Public, đúng tên, nộp link trên LMS

**Mục đích:** nộp đủ bằng chứng đúng chỗ để Lab Coach chấm được, tránh bị trừ điểm.
