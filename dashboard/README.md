# Anima Dashboard

React + TypeScript + Vite + Tailwind CSS frontend for Anima.

## Development

```bash
# From repo root (recommended — starts broker + backend + dashboard together)
pnpm dev

# Dashboard only (requires backend running separately)
pnpm dev:frontend
```

The dashboard runs on **http://localhost:3000** and proxies API requests to the backend at `localhost:8080`.

## Build

```bash
pnpm build
```

Production build outputs to `dashboard/dist/`.

## Architecture

- **`src/App.tsx`** — Main layout and component composition
- **`src/hooks/useApi.ts`** — API client hooks for all backend endpoints
- **`src/components/`** — UI components (DeviceList, ChatBar, SettingsPanel, etc.)
- **`src/index.css`** — Tailwind CSS entry point

The dashboard is a polling-based operator console that reflects backend state. All business logic lives in the Python backend — the frontend triggers backend actions and displays results.
