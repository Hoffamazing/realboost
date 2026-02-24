# RealBoost AI 🏠🤖
### AI-Powered Real Estate Marketing SaaS

Multi-tenant platform that automates advertising across Meta, Google, TikTok, and Waze — with AI lead qualification, hot lead alerts, and automated drip campaigns.

---

## Architecture

```
realboost/
├── frontend/          React + Tailwind (Vite)
│   └── src/
│       ├── api.js     All API calls to backend
│       └── ...        Pages, components, hooks
│
└── backend/           Python FastAPI
    ├── main.py        App entry point
    ├── models/
    │   └── database.py  SQLAlchemy models (PostgreSQL)
    ├── routers/
    │   ├── agents.py    Auth & registration
    │   ├── leads.py     Lead CRUD + AI qualification
    │   ├── campaigns.py Drip campaigns
    │   ├── ads.py       Ad platform integrations
    │   ├── billing.py   Stripe subscriptions
    │   ├── ai.py        AI generation endpoints
    │   └── webhooks.py  Twilio TwiML + platform callbacks
    ├── services/
    │   ├── ai_service.py         OpenAI GPT-4o integration
    │   └── notification_service.py  Twilio + SendGrid
    └── middleware/
        └── auth.py      JWT authentication
```

---

## Step-by-Step Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL (or Supabase account — recommended)
- Accounts: OpenAI, Stripe, Twilio, SendGrid, Meta Developers

---

### Step 1: Database (Supabase — free tier works)

1. Go to [supabase.com](https://supabase.com) → Create new project
2. Go to **Settings > Database > Connection String**
3. Copy the **Transaction pooler** URI (starts with `postgresql://`)
4. Change `postgresql://` to `postgresql+asyncpg://`
5. Paste into your `.env` as `DATABASE_URL`

Tables are created automatically on first startup via SQLAlchemy.

---

### Step 2: Backend Setup

```bash
cd backend
cp .env.example .env
# Fill in your .env values (see API Keys section below)

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

---

### Step 3: Frontend Setup

```bash
cd frontend
cp .env.example .env
# Set VITE_API_URL=http://localhost:8000

npm install
npm run dev
```

App available at: http://localhost:5173

---

## API Keys Setup

### OpenAI (Step 1 — AI qualification + email generation)
1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Create a new secret key
3. Add to `.env`: `OPENAI_API_KEY=sk-...`
4. Recommended: set a monthly spend limit in OpenAI dashboard
5. **Cost estimate**: ~$0.002 per lead conversation (GPT-4o pricing)

---

### Stripe (Step 3 — Subscriptions)

1. Go to [dashboard.stripe.com](https://dashboard.stripe.com)
2. **API Keys**: Developers > API Keys → copy Secret key
3. **Create Products**:
   - Go to Products > Add Product
   - Create "RealBoost Starter" — $99/month recurring
   - Create "RealBoost Pro" — $249/month recurring  
   - Create "RealBoost Team" — $499/month recurring
   - Copy each Price ID (starts with `price_`)
4. **Webhook**:
   - Developers > Webhooks > Add endpoint
   - URL: `https://your-api.com/api/billing/webhook`
   - Events to listen: `customer.subscription.*`, `invoice.payment_*`
   - Copy the Webhook signing secret (`whsec_...`)
5. **Local testing**: Install [Stripe CLI](https://stripe.com/docs/stripe-cli)
   ```bash
   stripe listen --forward-to localhost:8000/api/billing/webhook
   ```

---

### Meta Ads (Step 4 — Facebook/Instagram lead ads)

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. **Create App**: My Apps > Create App > Business type
3. **Add Products**: Add "Marketing API" and "Webhooks"
4. **Get App ID and Secret**: App Settings > Basic
5. **System User Token**:
   - Go to [business.facebook.com](https://business.facebook.com)
   - Settings > System Users > Add System User (Admin)
   - Generate Token with permissions: `ads_management`, `ads_read`, `leads_retrieval`
6. **Ad Account ID**: Found in Meta Ads Manager URL: `act_XXXXXXXXXX`
7. **Configure Webhook**:
   - App Dashboard > Webhooks > Page > leadgen subscription
   - Callback URL: `https://your-api.com/api/ads/meta/webhook/leads`
   - Verify token: same as `META_WEBHOOK_VERIFY_TOKEN` in your `.env`
8. **Important**: Set `special_ad_categories=["HOUSING"]` — Meta requires this for all real estate ads
9. **Lead forms**: Create in Meta Ads Manager > Lead Ads > Forms Library

---

### Twilio (Hot lead alerts + call connect)

1. Go to [console.twilio.com](https://console.twilio.com)
2. **Account SID + Auth Token**: visible on Console dashboard
3. **Buy phone numbers**: Phone Numbers > Manage > Buy a Number
   - Buy 2 numbers: one for SMS alerts, one for call connect
4. **Test SMS**: 
   ```bash
   python -c "
   from twilio.rest import Client
   c = Client('ACxxxx', 'auth_token')
   c.messages.create(body='Test from RealBoost!', from_='+1xxx', to='+1your_number')
   "
   ```
5. **Call Connect TwiML**: Your API auto-serves TwiML at `/api/webhooks/twiml/connect`

---

### SendGrid (Email delivery)

1. Go to [app.sendgrid.com](https://app.sendgrid.com)
2. Settings > API Keys > Create API Key (Full Access)
3. **Domain Authentication** (critical for deliverability):
   - Settings > Sender Authentication > Authenticate Your Domain
   - Add DNS records to your domain
4. **From address**: Must match your authenticated domain
5. Test: Verify your sender in SendGrid before sending production emails

---

## Deployment

### Backend — Railway (recommended, easiest)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Deploy
railway login
railway init
railway up

# Set environment variables in Railway dashboard
# Settings > Variables > add all from .env
```

### Backend — Render

1. New > Web Service > Connect GitHub repo
2. Build Command: `pip install -r requirements.txt`
3. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables in Render dashboard

### Frontend — Vercel

```bash
npm install -g vercel
cd frontend
vercel --prod
```

Set environment variable: `VITE_API_URL=https://your-backend.railway.app`

### Frontend — Netlify

1. Build command: `npm run build`
2. Publish directory: `dist`
3. Add environment variable: `VITE_API_URL=https://your-backend.railway.app`

---

## Production Checklist

- [ ] Change `JWT_SECRET_KEY` to a real 256-bit random key
- [ ] Switch Stripe from test keys (`sk_test_`) to live keys (`sk_live_`)
- [ ] Set up Supabase production project (enable connection pooling)
- [ ] Configure SendGrid domain authentication
- [ ] Set up Twilio phone numbers for production
- [ ] Enable Meta App in production mode (remove sandbox)
- [ ] Set CORS origins to your actual frontend domain in `main.py`
- [ ] Set up background job runner (Celery + Redis) for drip campaign scheduling
- [ ] Add rate limiting (slowapi) to prevent abuse
- [ ] Set up error monitoring (Sentry)
- [ ] Configure SSL/HTTPS for all endpoints (required for Meta webhooks)

---

## Subscription Plans

| Feature | Starter $99/mo | Pro $249/mo | Team $499/mo |
|---------|---------------|-------------|--------------|
| Leads/month | 200 | Unlimited | Unlimited |
| Ad Platforms | Meta + Google | All 4 | All 4 |
| AI Chat Qualification | ✅ | ✅ | ✅ |
| Drip Campaigns | 3 | Unlimited | Unlimited |
| AI Email Generator | ❌ | ✅ | ✅ |
| Hot Lead Call Connect | SMS only | SMS + Call | SMS + Call |
| AI Newsletter | ❌ | ✅ | ✅ |
| Birthday Automation | ❌ | ✅ | ✅ |
| Ad Budget Optimization | ❌ | ✅ | ✅ |
| Team Members | 1 | 1 | 5 |
| Team Dashboard | ❌ | ❌ | ✅ |

---

## Key API Endpoints

```
POST /api/agents/register          Register new agent (starts 14-day trial)
POST /api/agents/login             Login, get JWT token
GET  /api/agents/me                Get current agent profile

GET  /api/leads                    List all leads (filterable)
POST /api/leads                    Create lead
POST /api/leads/{id}/qualify       CORE: Send message → AI qualifies → returns response
GET  /api/leads/{id}/messages      Full conversation history
GET  /api/leads/stats/overview     Dashboard stats

POST /api/ai/generate-email        Generate marketing email with GPT-4o
POST /api/ai/generate-campaign     Generate full drip sequence
POST /api/ai/generate-newsletter   Generate market newsletter

GET  /api/ads/performance          All platform performance data
POST /api/ads/optimize             Run AI budget optimization
POST /api/ads/meta/campaigns       Create Meta lead gen campaign
POST /api/ads/meta/webhook/leads   Meta lead form webhook receiver

GET  /api/billing/plans            Available subscription plans
POST /api/billing/checkout         Create Stripe checkout session
POST /api/billing/portal           Open Stripe customer portal
POST /api/billing/webhook          Stripe event webhook handler
```

---

## Built With
- **Frontend**: React, Tailwind CSS, Vite
- **Backend**: FastAPI, SQLAlchemy (async), PostgreSQL
- **AI**: OpenAI GPT-4o
- **Payments**: Stripe
- **SMS/Calls**: Twilio
- **Email**: SendGrid
- **Ads**: Meta Marketing API, Google Ads API (stub), TikTok Marketing API (stub)
- **Database**: PostgreSQL via Supabase

---

*Built for real estate agents who know their market and want AI to handle the rest.*
