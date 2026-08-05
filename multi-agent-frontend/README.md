# Agent Workspace — React frontend

React UI for the **Multi-Agent Platform** chat and admin surfaces.

## Tech stack

| Technology | Purpose |
|------------|---------|
| React 19 + TypeScript | UI components |
| Vite 8 | Dev server & build |
| Tailwind CSS v4 | Design tokens & styling |
| React Router v7 | Routes (`/chat`, `/admin/*`) |

## Run locally

```bash
npm install
npm run dev
```

Open http://localhost:5173 — API requests proxy to `http://localhost:8000` (see `vite.config.ts`).

**Backend must be running:**

```bash
# from repo root
python -m gateway.main
```

## Features

| Feature | Status |
|---------|--------|
| Chat streaming (`POST /api/v1/chat/stream`) | Implemented |
| Session list & history | Implemented |
| Image upload for OCR | Implemented |
| Admin dashboard (`/admin/*`) | Implemented |
| API key in localStorage | Implemented (`multiagent_api_key`) |
| SSO / production auth | Planned |

## Project structure

```
src/
├── api/                 # client.ts, types — backend API
├── components/
│   ├── layout/          # TopNavBar, sidebars, layouts
│   └── ui/              # MaterialIcon, StarRating, …
├── pages/
│   ├── admin/           # Dashboard, knowledge, feedback, audit, models, logs
│   ├── chat/            # Main chat UI
│   └── settings/        # User settings
├── lib/storage.ts       # localStorage keys
└── routes/AppRoutes.tsx
```

## Routes

| Path | Page |
|------|------|
| `/chat` | New chat |
| `/chat/:sessionId` | Existing session |
| `/settings` | Settings |
| `/admin` | Dashboard |
| `/admin/knowledge` | Knowledge management |
| `/admin/feedback` | Feedback review |
| `/admin/audit` | Audit logs |
| `/admin/models` | Model & agent catalog |
| `/admin/logs` | System logs |

## Design system

- Colors: CSS variables in `src/index.css`
- Fonts: Inter (UI), JetBrains Mono (code/logs)
- Icons: Material Symbols via `<MaterialIcon />`
- Layout: 280px sidebar, 64px top bar

## Environment

No `.env` required for local dev — Vite proxies `/api` to port `8000`.

Optional: set API key in Settings UI (stored as `multiagent_api_key`).

## Related docs

- [FRONTEND-DESIGN-BRIEF.md](./FRONTEND-DESIGN-BRIEF.md) — full UI/UX spec
- [../docs/12-LOCAL-SETUP.md](../docs/12-LOCAL-SETUP.md) — backend setup
- [../docs/17-EXTERNAL-MCP.md](../docs/17-EXTERNAL-MCP.md) — MCP / OCR tools
