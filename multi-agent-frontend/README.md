# Agent Workspace — React Frontend

Ứng dụng React cho nền tảng **Enterprise Multi-Agent AI**, triển khai theo [FRONTEND-DESIGN-BRIEF.md](./FRONTEND-DESIGN-BRIEF.md) và các mockup HTML.

## Tech stack

| Công nghệ | Mục đích |
|-----------|----------|
| **React 19** + **TypeScript** | UI components |
| **Vite 8** | Build & dev server |
| **Tailwind CSS v4** | Design tokens + styling |
| **React Router v7** | Routing (`/chat`, `/admin/*`) |

## Chạy dự án

```bash
npm install
npm run dev
```

Mở http://localhost:5173 — API backend được proxy tới `http://localhost:8000` (xem `vite.config.ts`).

## Cấu trúc thư mục

```
src/
├── components/
│   ├── layout/          # TopNavBar, AdminSidebar, UserSidebar, layouts
│   └── ui/              # MaterialIcon, StarRating
├── pages/
│   ├── admin/           # Dashboard, Knowledge, Feedback, Audit, Models, Logs, Support
│   ├── chat/            # Giao diện chat chính
│   └── settings/        # Cài đặt người dùng
├── routes/AppRoutes.tsx # Định nghĩa route
└── index.css            # Design tokens (@theme)
```

## Routes

| Path | Trang |
|------|-------|
| `/chat` | Chat mới |
| `/chat/:sessionId` | Phiên chat |
| `/settings` | Cài đặt |
| `/admin` | Dashboard |
| `/admin/knowledge` | Quản trị tri thức |
| `/admin/feedback` | Phản hồi |
| `/admin/audit` | Audit logs |
| `/admin/models` | Model & Agent catalog |
| `/admin/logs` | System logs (kỹ thuật) |
| `/admin/support` | Trung tâm hỗ trợ |

## Design system

- **Màu sắc:** tokens trong `src/index.css` (`--color-secondary`, `--color-citation-knowledge`, …)
- **Typography:** Inter (UI), JetBrains Mono (code/logs)
- **Icons:** Material Symbols Outlined qua component `<MaterialIcon />`
- **Layout:** sidebar cố định 280px (`w-sidebar-width`), top bar 64px

## Bước tiếp theo (chưa implement)

- [ ] Kết nối API (`POST /api/v1/chat`, admin endpoints)
- [ ] Sources drawer khi click citation `[D1]`
- [ ] Upload wizard knowledge
- [ ] Chi tiết feedback/audit theo `traceId`
- [ ] Auth SSO / `X-API-Key`

## Tài liệu liên quan

- [FRONTEND-DESIGN-BRIEF.md](./FRONTEND-DESIGN-BRIEF.md) — spec đầy đủ UI/UX & API mapping
