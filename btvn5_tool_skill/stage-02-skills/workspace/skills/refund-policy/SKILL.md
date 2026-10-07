---
name: refund-policy
description: Trả lời khách hàng có được hoàn tiền hay không dựa trên tài liệu chính sách hoàn tiền trong workspace (data/policies/), chọn đúng phiên bản chính sách theo ngày mua. Dùng khi người dùng hỏi về hoàn tiền, trả hàng, điều kiện hoặc phí hoàn tiền của một đơn hàng.
---

# Refund policy

Hướng dẫn kết luận yêu cầu hoàn tiền theo đúng phiên bản chính sách.

## Các bước

1. Kiểm tra người dùng đã cung cấp đủ 3 thông tin:
   - **Ngày mua**
   - **Ngày yêu cầu hoàn**
   - **Trạng thái kích hoạt** sản phẩm (đã / chưa kích hoạt)

   Nếu thiếu bất kỳ thông tin nào, hỏi lại đúng thông tin còn thiếu và dừng, chưa kết luận. Không tự giả định giá trị mặc định (ví dụ không tự coi là "chưa kích hoạt").
2. Dùng `list_files` với `data/policies` để xem các tài liệu chính sách hiện có. Không đoán tên file; tên file có thể thay đổi.
3. Đọc từng tài liệu bằng `read_file` và xác định **phạm vi hiệu lực** ghi trong nội dung (áp dụng cho ngày mua nào). Không dựa vào tên file để suy ra phạm vi.
4. Chọn tài liệu có phạm vi hiệu lực chứa **ngày mua** (không phải ngày yêu cầu hoàn). Nếu không có hoặc có nhiều hơn một tài liệu khớp, báo rõ cho người dùng và không kết luận.
5. Tính số ngày đã qua = ngày yêu cầu hoàn − ngày mua (tính theo ngày lịch).
6. Đối chiếu với tài liệu đã chọn: thời hạn hoàn tiền, điều kiện kích hoạt, phí hoàn tiền. Chỉ dùng điều khoản có trong tài liệu; không bổ sung quy định từ kiến thức chung.
7. Đọc template `references/answer-template.md` trong thư mục skill này, tức `skills/refund-policy/references/answer-template.md`, và trả lời đúng các mục của template.
8. Nếu `list_files` hoặc `read_file` trả lỗi, báo lỗi cho người dùng và dừng; không bịa nội dung chính sách.
