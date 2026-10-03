Model: anthropic:claude-haiku-4-5-20251001 · 3 lần/tổ hợp

| Kịch bản | Mẫu | Đúng | Outcome | Lượt LLM | Lượt tool | Token | Giây | USD |
|---|---|---|---|---|---|---|---|---|
| binh_thuong | react | 3/3 | dat_muc_tieu×3 | 5.0 | 5.0 | 14193 | 10.1 | 0.0176 |
| binh_thuong | plan_execute | 3/3 | dat_muc_tieu×3 | 6.0 | 5.0 | 14245 | 7.1 | 0.0164 |
| binh_thuong | lai | 3/3 | dat_muc_tieu×3 | 6.0 | 5.0 | 14243 | 7.3 | 0.0164 |
| doi_giua_chung | react | 3/3 | dat_muc_tieu×3 | 7.0 | 7.0 | 21318 | 11.8 | 0.0258 |
| doi_giua_chung | plan_execute | 0/3 | ke_hoach_hong×3 | 3.0 | 2.0 | 5877 | 4.3 | 0.0074 |
| doi_giua_chung | lai | 3/3 | dat_muc_tieu×3 | 10.0 | 7.0 | 23066 | 14.0 | 0.0276 |
| tool_loi | react | 3/3 | tu_dung_chua_dat×3 | 5.0 | 4.0 | 14273 | 12.1 | 0.0184 |
| tool_loi | plan_execute | 3/3 | ke_hoach_hong×3 | 3.0 | 2.0 | 5879 | 4.2 | 0.0074 |
| tool_loi | lai | 3/3 | lap×3 | 9.0 | 5.0 | 18410 | 15.1 | 0.0238 |
| can_duyet | react | 3/3 | cho_nguoi×3 | 3.0 | 3.0 | 7633 | 6.0 | 0.0101 |
| can_duyet | plan_execute | 3/3 | cho_nguoi×3 | 4.0 | 3.0 | 8493 | 5.1 | 0.0102 |
| can_duyet | lai | 3/3 | cho_nguoi×3 | 4.0 | 3.0 | 8496 | 5.3 | 0.0103 |

**Tổng theo mẫu (mọi kịch bản):**

| Mẫu | Tỉ lệ đúng | Lượt LLM TB | Token TB | Giây TB | USD TB | Dừng có bàn giao | Bịa dữ kiện |
|---|---|---|---|---|---|---|---|
| react | 12/12 | 5.0 | 14354 | 10.0 | 0.0180 | 6 | 0 |
| plan_execute | 9/12 | 4.0 | 8624 | 5.2 | 0.0104 | 9 | 0 |
| lai | 12/12 | 7.2 | 16054 | 10.4 | 0.0195 | 6 | 0 |
