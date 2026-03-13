# 💸 Fintoc Finance App

A personal finance web app where users connect their own Chilean bank accounts via Fintoc, and view all their movements in a beautiful phone-style UI.

**Stack:** Vercel (frontend + serverless API) · Supabase (auth + database) · Fintoc (bank data)

---

## 🗂 Project structure

```
├── api/
│   ├── _lib/
│   │   ├── auth.py        ← JWT auth helper
│   │   └── db.py          ← Supabase admin client
│   ├── config.py          ← GET  /api/config  (public keys)
│   ├── connect.py         ← POST /api/connect (exchange Fintoc token)
│   ├── sync.py            ← POST /api/sync    (fetch new movements)
│   └── movements.py       ← GET  /api/movements
├── public/
│   └── index.html         ← Full frontend (auth + phone UI)
├── supabase/
│   └── migrations/
│       └── 001_schema.sql ← Run once in Supabase SQL editor
├── .env.example           ← Copy to .env and fill in secrets
├── .gitignore
├── requirements.txt
└── vercel.json
```

---

## 🚀 Deploy in 5 steps

### 1. Set up Supabase
1. Create a project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** → **New Query**
3. Paste the contents of `supabase/migrations/001_schema.sql` and run it
4. Go to **Project Settings → API** and copy:
   - `URL`
   - `anon public` key
   - `service_role` key *(keep this secret)*

### 2. Set up Fintoc
1. Create an account at [app.fintoc.com](https://app.fintoc.com)
2. Go to **API Keys** and copy your `Public Key` and `Secret Key`

### 3. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 4. Deploy to Vercel
1. Go to [vercel.com](https://vercel.com) → **Add New Project**
2. Import your GitHub repo
3. Go to **Project Settings → Environment Variables** and add:

| Variable | Value |
|----------|-------|
| `FINTOC_SECRET_KEY` | `sk_live_...` |
| `FINTOC_PUBLIC_KEY` | `pk_live_...` |
| `SUPABASE_URL` | `https://xxx.supabase.co` |
| `SUPABASE_ANON_KEY` | `eyJ...` |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJ...` |

4. Click **Deploy** — done! ✅

### 5. Configure Supabase Auth redirect
In Supabase → **Authentication → URL Configuration**, add your Vercel domain:
```
https://your-app.vercel.app
```

---

## 🔒 Security model

- Users sign up/in via Supabase Auth (email + password)
- Every API call requires a valid Supabase JWT in the `Authorization` header
- Each user can only see their own data (enforced by Row Level Security in Postgres)
- The `SERVICE_ROLE_KEY` is only used server-side — never sent to the browser
- The `.env` file is gitignored — secrets only live in Vercel's environment

---

## 🧪 Local development

```bash
# Install Vercel CLI
npm i -g vercel

# Copy env file and fill in your secrets
cp .env.example .env

# Run locally
vercel dev
```

The app will be at `http://localhost:3000`.
