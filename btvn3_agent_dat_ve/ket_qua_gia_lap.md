Model: model giả lập (token là ước lượng) · 1 lần/tổ hợp

| Kịch bản | Mẫu | Đúng | Outcome | Lượt LLM | Lượt tool | Token | Giây | USD |
|---|---|---|---|---|---|---|---|---|
| binh_thuong | react | 1/1 | dat_muc_tieu | 5.0 | 5.0 | 5391 | 0.0 | 0.0065 |
| binh_thuong | plan_execute | 1/1 | dat_muc_tieu | 6.0 | 5.0 | 6864 | 0.0 | 0.0083 |
| binh_thuong | lai | 1/1 | dat_muc_tieu | 6.0 | 5.0 | 6864 | 0.0 | 0.0083 |
| doi_giua_chung | react | 1/1 | dat_muc_tieu | 7.0 | 7.0 | 8180 | 0.0 | 0.0097 |
| doi_giua_chung | plan_execute | 0/1 | ke_hoach_hong | 3.0 | 2.0 | 3023 | 0.0 | 0.0038 |
| doi_giua_chung | lai | 1/1 | dat_muc_tieu | 10.0 | 7.0 | 12381 | 0.0 | 0.0149 |
| tool_loi | react | 1/1 | lap | 4.0 | 4.0 | 4088 | 0.0 | 0.0049 |
| tool_loi | plan_execute | 1/1 | ke_hoach_hong | 3.0 | 2.0 | 3023 | 0.0 | 0.0038 |
| tool_loi | lai | 1/1 | lap | 7.0 | 4.0 | 8011 | 0.0 | 0.0098 |
| can_duyet | react | 1/1 | cho_nguoi | 3.0 | 3.0 | 2873 | 0.0 | 0.0035 |
| can_duyet | plan_execute | 1/1 | cho_nguoi | 4.0 | 3.0 | 4170 | 0.0 | 0.0052 |
| can_duyet | lai | 1/1 | cho_nguoi | 4.0 | 3.0 | 4170 | 0.0 | 0.0052 |

**Tổng theo mẫu (mọi kịch bản):**

| Mẫu | Tỉ lệ đúng | Lượt LLM TB | Token TB | Giây TB | USD TB | Dừng có bàn giao | Bịa dữ kiện |
|---|---|---|---|---|---|---|---|
| react | 4/4 | 4.8 | 5133 | 0.0 | 0.0062 | 2 | 0 |
| plan_execute | 3/4 | 4.0 | 4270 | 0.0 | 0.0053 | 3 | 0 |
| lai | 4/4 | 6.8 | 7856 | 0.0 | 0.0096 | 2 | 0 |
