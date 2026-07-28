# Database Query Skill

## Quy tắc bắt buộc

1. **CHỈ dùng SELECT** — không INSERT, UPDATE, DELETE, DROP, ALTER
2. **Luôn có LIMIT** — mặc định 100 rows, tối đa 500
3. **Không biết schema → gọi `describe_table` trước** khi query
4. **Trả lời bằng tiếng Việt**, kèm SQL đã chạy trong code block
5. **Không tìm thấy dữ liệu** → nói rõ và gợi ý query thay thế

## Schema chính (PostgreSQL — schema `app`)

### Bảng `app.clients`

| Column | Type | Mô tả |
|--------|------|--------|
| id | SERIAL | Primary key |
| name | VARCHAR | Tên khách hàng |
| tax_code | VARCHAR | Mã số thuế |
| email | VARCHAR | Email liên hệ |

### Bảng `app.contracts`

| Column | Type | Mô tả |
|--------|------|--------|
| id | SERIAL | Primary key |
| code | VARCHAR | Mã hợp đồng |
| client_id | INTEGER | FK → clients.id |
| title | TEXT | Tiêu đề |
| status | VARCHAR | active / expired / draft |
| value_vnd | BIGINT | Giá trị VND |

## Ví dụ query đúng

```sql
SELECT COUNT(*) AS total FROM app.contracts WHERE status = 'active' LIMIT 100;

SELECT c.code, c.title, cl.name AS client_name
FROM app.contracts c
JOIN app.clients cl ON c.client_id = cl.id
WHERE cl.name ILIKE '%ABC%'
LIMIT 10;
```

## Output format

- Tóm tắt kết quả bằng tiếng Việt
- Kèm SQL trong code block
