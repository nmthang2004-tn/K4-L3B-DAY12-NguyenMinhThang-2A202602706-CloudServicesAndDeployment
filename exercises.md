# Phiếu Phản Ánh — K4 Level 3B, Ngày 12

**Họ và tên:** Nguyễn Minh Thắng  
**Mã học viên:** 2A202602706

---

### Câu 1 — Fail fast (CP1)

Khi đưa Agent lên cloud, nếu tôi quên khai báo `AGENT_API_KEY` mà chương trình vẫn dùng khóa mặc định `"changeme"`, bất cứ ai biết hoặc đoán được khóa này đều có thể gửi yêu cầu tới `/ask` và tiêu tốn ngân sách API. Khóa đó cũng có thể bị dùng chung giữa các môi trường mà tôi không nhận ra. Việc đặt `agent_api_key` là trường bắt buộc khiến Pydantic báo lỗi ngay khi khởi động nếu thiếu secret, thay vì để một service có vẻ hoạt động bình thường nhưng thực chất không an toàn. Nhờ vậy, tôi biết cần sửa cấu hình trên dashboard trước khi public URL nhận request.

---

### Câu 2 — Log cho máy đọc (CP1)

Trong `log_event()`, mỗi sự kiện được serialize thành một JSON trên đúng một dòng. Ví dụ định dạng của sự kiện `/ask` như sau (đây là **ví dụ minh họa**, không phải log thực tế đã sao chép từ deployment):

```json
{"event":"ask_completed","level":"info","timestamp":"2026-09-29T04:30:00+00:00","user_id":"sv-test","tokens_in":20,"tokens_out":35,"cost_usd":0.0001}
```

Thứ nhất, tôi có thể lọc các bản ghi theo `event`, `user_id` hoặc khoảng `timestamp` để tìm request cần kiểm tra, thay vì đọc thủ công một chuỗi `print("đã trả lời xong")` không có cấu trúc. Thứ hai, hệ thống thu thập log có thể cộng `cost_usd`, thống kê token hoặc tạo cảnh báo khi chi phí tăng bất thường. Tôi cũng dùng `ensure_ascii=False` để tiếng Việt giữ nguyên khi log được đẩy lên cloud. Khi nộp bằng chứng thực nghiệm, tôi cần thay ví dụ ở trên bằng đúng một dòng `ask_completed` đã lấy từ log sau khi gọi `/ask` thành công.

---

### Câu 3 — Kích thước image (CP2)

Tôi đã thử chạy cả hai lệnh build trên PowerShell. Kết quả quan sát được là bản `agent:multi` build thành công với **14/14 bước**, trong đó các bước tạo virtual environment, cài dependencies và copy source đều hiển thị `CACHED`. Thời gian build hiển thị khoảng **1,5 giây**. Ngược lại, lệnh `docker build -f Dockerfile.single -t agent:single .` chỉ báo `transferring dockerfile: 2B` và kết thúc trước khi có các bước build của image; vì vậy tôi **chưa có image single-stage hợp lệ để đo và đối chiếu dung lượng**. Log build cũng không hiển thị dung lượng của image multi-stage.

| Bản | Dung lượng đo thực tế |
|-----|-----------------------|
| 1 stage (`agent:single`) | Chưa đo được: cần tạo lại `Dockerfile.single` hợp lệ từ bản starter |
| Multi-stage (`agent:multi`) | Build thành công; cần chạy `docker image ls agent:multi` để lấy số MB |

Lý do kỳ vọng bản mới gọn hơn là Dockerfile ban đầu dùng `python:3.11` và `COPY . .`, trong khi bản cải tiến dùng `python:3.11-slim`, tách `builder` và `runtime`, chỉ copy virtual environment cùng mã nguồn cần chạy. Nhờ vậy, stage runtime không phải giữ lại những thành phần chỉ phục vụ build. Tuy nhiên, tôi không thể khẳng định số MB tiết kiệm khi chưa đo đủ hai image; kích thước cuối vẫn phụ thuộc các thư viện trong `requirements.txt`.

Để hoàn tất phép đo, tôi cần lưu lại Dockerfile một stage gốc thành `Dockerfile.single` rồi chạy:

```powershell
docker build -f Dockerfile.single -t agent:single .
docker build -t agent:multi .
docker image ls --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | findstr /C:"agent:single" /C:"agent:multi"
```

Sau đó thay hai ô chưa đo bằng dung lượng thật, không dùng thời gian build hoặc chữ `CACHED` làm số đo kích thước image.

---

### Câu 4 — Thứ tự lệnh trong Dockerfile (CP2)

Trong Dockerfile mới, tôi copy `requirements.txt` và chạy `pip install` trước khi copy `app/`, `utils/`. Nếu tôi chỉ sửa một ký tự trong `app/main.py` rồi build lại, những layer trước bước copy source (base image, tạo virtual environment, copy requirements và cài dependency) có thể được dùng lại từ cache nếu đầu vào của chúng không đổi. Docker chỉ phải làm mới bước copy source và các bước phía sau bị ảnh hưởng. Nếu đặt `COPY . .` trước `RUN pip install`, thay đổi nhỏ trong `main.py` cũng làm mất cache của layer copy toàn bộ project, kéo theo việc chạy lại cài đặt dependencies không cần thiết. Vì vậy, thứ tự Dockerfile ảnh hưởng trực tiếp đến thời gian build mỗi lần cập nhật code.

---

### Câu 5 — Vì sao không chạy bằng root (CP2)

Giả sử endpoint Python có lỗ hổng cho phép kẻ tấn công thực thi lệnh trong container. Nếu process chạy bằng root, kẻ tấn công có quyền root **bên trong container**, từ đó có thể sửa những file container được phép truy cập, đọc dữ liệu hoặc tác động tới tài nguyên host đã mount vào container nếu quyền cho phép. Khi còn có thêm cấu hình Docker nguy hiểm như privileged mode, mount Docker socket hay một lỗ hổng thoát container, tác động tới host có thể nghiêm trọng hơn. Lệnh tạo user thường và `USER appuser` làm process FastAPI chạy với quyền hạn chế, giảm những thao tác mà mã độc có thể thực hiện ngay từ bước chiếm quyền trong container. Đây là lớp giảm thiểu thiệt hại, không có nghĩa non-root tự nó loại bỏ mọi khả năng thoát container hoặc chiếm quyền host.

---

### Câu 6 — Cửa sổ trượt (CP3)

Nếu đếm theo phút đồng hồ với hạn mức 10 request/phút, một user có thể gửi **20 request trong khoảng 2 giây**: gửi 10 request ở thời điểm 10:00:59, rồi gửi tiếp 10 request ở 10:01:00 khi bộ đếm vừa reset. Hai đợt đều hợp lệ theo từng phút lịch, nhưng tổng lưu lượng trong thời gian rất ngắn vẫn là 20. Sliding window nhìn lại đúng 60 giây gần nhất nên các request ở cuối phút trước vẫn được tính vào cửa sổ mới. Trong bài, tôi dùng Redis Sorted Set: xóa bản ghi cũ, đếm số request còn hiệu lực, chỉ ghi nhận request mới nếu chưa đạt giới hạn và dùng member kết hợp timestamp với UUID để tránh hai member trùng tên.

---

### Câu 7 — Rate limit và cost guard (CP3)

Rate limit giới hạn **tần suất/số lần gọi** trong 60 giây, còn cost guard giới hạn **tiền đã sử dụng** theo user và tháng UTC. Ví dụ một user mới gửi 2 request trong phút nên chưa chạm giới hạn 10, nhưng đã tiêu gần hết 10 USD ngân sách tháng; nếu chi phí ước tính của request tiếp theo làm tổng vượt 10 USD, cost guard phải trả 402 dù rate limit vẫn cho qua. Chiều ngược lại, một user vừa gửi đủ 10 request trong 60 giây nhưng tất cả đều rất rẻ, tổng chi phí tháng còn thấp hơn ngân sách; request thứ 11 phải bị rate limiter trả 429 dù cost guard vẫn còn cho phép. Hai cơ chế phải phối hợp và kiểm tra trước khi gọi LLM. Với code lab hiện tại, `guard.check(user_id)` dùng chi phí ước tính mặc định bằng 0; muốn bảo vệ ngân sách chặt chẽ ở production cần ước tính và giữ trước quota cho các request đồng thời.

---

### Câu 8 — /health khác /ready (CP4)

Nếu gộp hai endpoint và bắt liveness cũng phải ping Redis, khi Redis mất kết nối trong 30 giây thì cả 3 Agent container đều có thể trả 503 cho healthcheck dù các process FastAPI vẫn sống. Orchestrator có thể coi cả ba instance bị hỏng và lần lượt restart chúng. Redis vẫn đang lỗi nên các container vừa khởi động lại tiếp tục thất bại khi ping, tạo một vòng lặp restart không cần thiết và làm hệ thống mất ổn định hơn. Khi tách endpoint, `/health` chỉ xác nhận process còn sống nên vẫn trả 200 trong lúc Redis gián đoạn; `/ready` trả 503 để load balancer ngừng phân phối request mới tới instance chưa sẵn sàng. Khi Redis phục hồi, `/ready` có thể trả 200 mà không cần restart hàng loạt Agent.

---

### Câu 9 — Stateless (CP4)

Với cùng `X-User-Id`, các instance cần nhìn thấy cùng một lịch sử hội thoại. Khi history được lưu vào Redis List theo key `history:<user_id>`, mỗi request đọc cùng dữ liệu chung, sau đó append hai message (user và assistant). Vì vậy `history_length` trả về **độ dài trước khi append** sẽ tăng theo số message đã có: thường là 0, 2, 4, 6... và khi chạm giới hạn lưu 20 message thì ổn định ở 20, giả sử không có request khác đồng thời và TTL chưa hết. Nếu thay bằng dict Python trong RAM, mỗi container có lịch sử riêng: request đi tới instance A có thể trả 0 rồi 2, trong khi request tiếp theo tới B lại trả 0, nên số liệu có thể nhảy lùi hoặc khác nhau tùy instance nhận request. Redis giúp các replica chia sẻ state và giữ lịch sử qua restart của riêng Agent; mức bền vững khi Redis restart còn tùy cấu hình persistence của Redis. Để scale Compose trên cùng host, trước tiên phải xử lý xung đột mapping `8000:8000` của nhiều replica.

---

### Câu 10 — Deploy thật (CP5)

Lỗi thực tế tôi gặp khi deploy lên Railway là `/health` trả HTTP 200 nhưng `/ready` lại trả HTTP 503 với response `{"status":"not ready","redis":false}`. Ban đầu tôi tưởng do domain hoặc deploy chưa thành công, nhưng deploy logs cho thấy Uvicorn đã `Application startup complete` và request đã vào được endpoint. Đối chiếu code `ready()` cho thấy nhánh 503 này xảy ra khi `store.ping()` trả `False`, tức điểm cần kiểm tra nằm ở kết nối Redis chứ không phải public URL. Tôi đã kiểm tra việc khai báo `REDIS_URL` dưới dạng reference ở service Agent, kiểm tra deployment/commit và bổ sung chẩn đoán cho Redis ping; tuy nhiên, các bằng chứng lúc đó chưa xác định chắc chắn nguyên nhân gốc vì `ping()` ban đầu bắt mọi exception và chỉ trả `False`. Để tiếp tục đúng tiến độ CP5, tôi chuyển sang triển khai bằng Render Blueprint (`render.yaml`), khai báo Web Service và Render Key Value, truyền `REDIS_URL` qua internal connection string thay vì tự điền địa chỉ thủ công. Bài học tôi rút ra là phải phân biệt liveness với readiness và kiểm tra cấu hình thực sự bên trong deployment, không chỉ nhìn trạng thái Online trên dashboard. Việc Render đạt hay chưa cần đối chiếu kết quả `/health`, `/ready`, `/ask` và `pytest tests/test_cp5.py -v` thực tế.
