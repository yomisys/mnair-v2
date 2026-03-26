# MNAIR Admin Dashboard

React-based admin dashboard for the Make Nigeria AI Ready (MNAIR) platform.

## Features

- **Authentication**: Secure login for admin users
- **Dashboard**: Real-time analytics and KPI overview
- **Material-UI**: Modern, responsive design with Nigerian green theme
- **TypeScript**: Type-safe development
- **Vite**: Fast development and build tooling

## Tech Stack

- React 18
- TypeScript 5
- Vite 4
- Material-UI 5
- React Router 6
- Axios
- Chart.js 4

## Setup

1. Install dependencies:
```bash
npm install
```

2. Create `.env` file:
```bash
cp .env.example .env
```

3. Start development server:
```bash
npm run dev
```

The app will run on `http://localhost:3000`

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Type check with TypeScript

## Project Structure

```
frontend/
├── src/
│   ├── contexts/       # React contexts (Auth)
│   ├── pages/          # Page components
│   ├── services/       # API client
│   ├── App.tsx         # Main app component
│   ├── main.tsx        # Entry point
│   └── theme.ts        # Material-UI theme
├── index.html
├── vite.config.ts
└── tsconfig.json
```

## Environment Variables

- `VITE_API_URL` - Backend API URL (default: http://localhost:8000)

## Admin Login

Admin accounts require both phone number and password. Regular learners use passwordless authentication.

## Features (MVP)

This is an MVP version with:
- ✅ Admin login
- ✅ Dashboard with key metrics
- ✅ Authentication context
- ✅ API client with interceptors
- ⏳ Full analytics charts (coming soon)
- ⏳ User management (coming soon)
- ⏳ Certificate management (coming soon)

## Building for Production

```bash
npm run build
```

The build output will be in the `dist/` directory.

## License

MIT
