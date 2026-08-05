# Database Query Skill

## Mandatory rules

1. **SELECT only** — no INSERT, UPDATE, DELETE, DROP, ALTER
2. **Always use LIMIT** — default 100 rows, maximum 500
3. **Unknown schema → call `describe_table` first** before querying
4. **Respond in the user's language**, include executed SQL in a code block
5. **No data found** → state clearly and suggest alternative queries

## Main schema (PostgreSQL — schema `app`)

### Table `app.clients`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| name | VARCHAR | Client name |
| tax_code | VARCHAR | Tax ID |
| email | VARCHAR | Contact email |

### Table `app.contracts`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| code | VARCHAR | Contract code |
| client_id | INTEGER | FK → clients.id |
| title | TEXT | Title |
| status | VARCHAR | active / expired / draft |
| value_vnd | BIGINT | Value in VND |

## Correct query examples

```sql
SELECT COUNT(*) AS total FROM app.contracts WHERE status = 'active' LIMIT 100;

SELECT c.code, c.title, cl.name AS client_name
FROM app.contracts c
JOIN app.clients cl ON c.client_id = cl.id
WHERE cl.name ILIKE '%ABC%'
LIMIT 10;
```

## Output format

- Summarize results in the user's language
- Include SQL in a code block
