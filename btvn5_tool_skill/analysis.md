# Analysis — Tra cứu chính sách hoàn tiền theo đúng phiên bản

Model: `claude-haiku-4-5` (qua OpenAI-compatible endpoint của Anthropic).
Project chạy kiểm tra: `stage-02-skills/`.

## 1. Stage 00 — Agent chưa có tool

- Trace: `stage-00-chat/traces/20261007-102926_441fc3df_turn01_f8b92c6a.jsonl`
  - L2 (`model_request`): `tools: []` — agent không có tool nào.
  - L3 (`model_response`): `tool_calls_requested: []`.
- Câu hỏi trường hợp A, không dán nội dung chính sách.
- Kết quả: agent tính đúng 8 ngày nhưng không kết luận được, hỏi lại chính sách; có đoán
  "thường 7–30 ngày → có khả năng được hoàn" — trái với đáp án đúng (không được hoàn).

**Agent còn thiếu:**

| Thiếu | Cụ thể |
|---|---|
| Thông tin | Nội dung chính sách; việc có 2 phiên bản đổi từ 2026-10-01 |
| Khả năng (tool) | Không liệt kê / đọc được file trong `data/policies/` |
| Quy trình (skill) | Không có hướng dẫn chọn chính sách theo ngày mua, tính hạn, phí, hỏi thêm khi thiếu thông tin |

## 2. Stage 01 — Tool `list_files`

Mã nguồn (giống nhau ở cả hai project): `stage-01-files/tools/files.py`, `stage-02-skills/tools/files.py` (`_list`, `list_files`).
Đăng ký: `tools/__init__.py` và `agent.py` (`TOOLS = [read_file, write_file, list_files]`) của từng project.

Tái sử dụng `_resolve` / `_error` của `read_file`: path được resolve (kể cả symlink) rồi kiểm tra
vẫn nằm trong workspace; mục con là symlink trỏ ra ngoài workspace bị bỏ qua.

**Kết quả kiểm tra tool** (gọi trực tiếp `_list` trên workspace thật):

| Input | Kết quả | Đạt |
|---|---|---|
| `data/policies` | `ok: true`, 2 mục `type: "file"`, sắp xếp theo tên | ✅ |
| `.` | Chỉ mục trực tiếp: `.lab-workspace`, `data`, `output`, `skills` (không đệ quy); thư mục có `type: "directory"` | ✅ |
| `../` | `PATH_OUTSIDE_WORKSPACE` | ✅ |
| `C:/Windows` (tuyệt đối) | `PATH_OUTSIDE_WORKSPACE` | ✅ |
| `data/khong-co` | `DIR_NOT_FOUND` (không trả danh sách rỗng) | ✅ |
| `data/policies/policy-from-oct.md` (là file) | `NOT_A_DIRECTORY` | ✅ |
| Schema gửi model | `tools: ['read_file', 'write_file', 'list_files']` (L2 mọi trace stage-02) | ✅ |

Test suite: `stage-01-files` → 34 passed; `stage-02-skills` → 41 passed (`uv run pytest`).

## 3. Stage 02 — Skill `refund-policy`

- `stage-02-skills/workspace/skills/refund-policy/SKILL.md`
  - Frontmatter `name`, `description` (nhiệm vụ + điều kiện dùng).
  - Hỏi lại nếu thiếu ngày mua / ngày yêu cầu hoàn / trạng thái kích hoạt; không tự giả định.
  - Dùng `list_files("data/policies")` để tìm tài liệu, **không ghi cứng tên file**.
  - Đọc **phạm vi hiệu lực trong nội dung** tài liệu, chọn theo **ngày mua**.
- `stage-02-skills/workspace/skills/refund-policy/references/answer-template.md`
  — chính sách áp dụng, số ngày đã qua, kết luận, phí, đường dẫn tài liệu căn cứ.
- Tài liệu chính sách: `stage-02-skills/workspace/data/policies/` (sau bước đổi tên:
  `chinh-sach-1.md` = trước 2026-10-01, `chinh-sach-2.md` = từ 2026-10-01).

Skill được catalog nhận (`skills/refund-policy/SKILL.md`, `diagnostics: []`).

## 4. Kiểm tra

Mọi trace là lượt 1 (`turn01`) của một cuộc trò chuyện mới; câu hỏi không nhắc tên skill,
tên file hay thứ tự gọi tool. Đường dẫn trace tương đối `stage-02-skills/traces/`.

| Ca | Kỳ vọng | Kết luận của agent | Đạt |
|---|---|---|---|
| A | Chính sách cũ; 8 ngày; không đủ điều kiện | Chính sách trước tháng 10; 8 ngày (hạn 7); không đủ điều kiện; phí: không áp dụng | ✅ |
| B | Chính sách mới; 10 ngày; đủ điều kiện, không phí | Chính sách từ tháng 10; 10 ngày (hạn 14); đủ điều kiện; không thu phí | ✅ |
| Đổi tên — A | Như A, tìm được file mới | Như A; căn cứ `data/policies/chinh-sach-1.md` | ✅ |
| Đổi tên — B | Như B, tìm được file mới | Như B; căn cứ `data/policies/chinh-sach-2.md` | ✅ |
| Thiếu thông tin | Hỏi trạng thái kích hoạt, chưa kết luận | Hỏi "Bạn đã kích hoạt sản phẩm hay chưa?"; không kết luận | ✅ |

### Vị trí bằng chứng trong trace

**A** — `20261007-103907_670dc5d7_turn01_1458f4be.jsonl`
- L4: `read_file skills/refund-policy/SKILL.md` (load skill)
- L8: `list_files data/policies`
- L12–L13: `read_file data/policies/policy-from-oct.md`, `policy-before-oct.md`
- L14: `read_file skills/refund-policy/references/answer-template.md`
- L19–L20: trả lời cuối, không gọi thêm tool

**B** — `20261007-104024_2cdccf7b_turn01_dac54e7e.jsonl`
- L4 load skill → L8 `list_files data/policies` → L12–L13 đọc 2 chính sách → L14 đọc template → L20 kết thúc

**Đổi tên — A** — `20261007-104926_5d9f3da4_turn01_c3463e40.jsonl`
- L4 load skill
- L8: `list_files data/policies` → tên mới
- L12–L13: `read_file data/policies/chinh-sach-1.md`, `chinh-sach-2.md` (tên mới, lấy từ kết quả `list_files`, không dùng tên cũ)
- L18: đọc template; L22 kết thúc

**Đổi tên — B** — `20261007-105026_d5a7f392_turn01_0c54639b.jsonl`
- L4 load skill → L8 `list_files data/policies` → L12–L13 đọc `chinh-sach-1.md`, `chinh-sach-2.md` → L18 đọc template → L22 kết thúc

**Thiếu thông tin** — `20261007-104139_1030ed14_turn01_4f9b2c13.jsonl`
- L4: `read_file skills/refund-policy/SKILL.md`
- L7: `tool_calls_requested: []` — không đọc chính sách, không kết luận
- L8: kết thúc với câu hỏi lại trạng thái kích hoạt

## 5. Câu hỏi cuối

**Vì sao cần tool để tìm file và skill để hướng dẫn chọn chính sách? Nếu agent chưa có tool tìm file,
việc sửa prompt có giải quyết được yêu cầu đổi tên file không?**

Tool và skill giải quyết hai thiếu hụt khác nhau:

- **Tool `list_files` cho agent *khả năng* quan sát trạng thái hiện tại của workspace.** Tên file là
  dữ liệu nằm ngoài model; nó chỉ biết được qua một lần gọi tool trả về kết quả thật lúc chạy.
  `read_file` thôi là chưa đủ, vì phải biết đúng path mới đọc được.
- **Skill cho agent *quy trình*:** cần đủ 3 thông tin nào, tìm tài liệu ở đâu, chọn theo ngày mua
  (không theo ngày yêu cầu, không theo tên file), tính hạn, phí, trả lời theo template. Skill chỉ được
  load khi task khớp description, nên không chiếm context của các task khác. Tool không có quy trình
  thì agent có thể đọc file nhưng chọn sai phiên bản hoặc kết luận khi thiếu thông tin
  (như Stage 00 đã đoán "có khả năng được hoàn").

**Sửa prompt không giải quyết được việc đổi tên file.** Prompt là văn bản tĩnh viết từ trước:

- Ghi cứng tên file vào prompt → đổi tên là `read_file` trả `FILE_NOT_FOUND`; agent không có cách
  nào tự tìm tên mới.
- Bảo agent "hãy tìm file chính sách" mà không cấp tool liệt kê → agent chỉ có thể đoán path.
- Dán nội dung chính sách vào prompt → không còn phụ thuộc tên file, nhưng phải sửa prompt mỗi lần
  tài liệu thay đổi, tài liệu luôn chiếm context, và không còn là "tìm theo đúng phiên bản trong workspace".

Trace đổi tên cho thấy điều ngược lại: không sửa prompt hay skill, agent vẫn gọi `list_files`
(L8), thấy `chinh-sach-1.md` / `chinh-sach-2.md`, đọc phạm vi hiệu lực trong nội dung và chọn đúng.
Prompt chỉ hướng dẫn được *cách làm*; muốn biết *thực tế đang có gì* thì phải có tool.
