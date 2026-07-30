# PackWatch — from prototype to public product

This is the architecture plan and deployment path for turning the dashboard
prototype into a real, always-on public website. It's written so you (or a
developer you hire) can follow it step by step.

## 1. The pieces

```
 ┌─────────────┐     every N min      ┌──────────────┐
 │  scraper.py │ ──────────────────► │  packwatch.db │  (SQLite → Postgres
 │  (cron job) │                      │  (listings)   │   once you have users)
 └─────────────┘                      └──────┬───────┘
                                              │
                                       ┌──────▼───────┐
                                       │   api.py      │  FastAPI, read-only
                                       │  (REST API)   │  endpoints for deals
                                       └──────┬───────┘
                                              │ fetch()
                                       ┌──────▼───────┐
                                       │  Frontend     │  the dashboard you
                                       │  (React site) │  already have
                                       └───────────────┘
                                              │
                                       ┌──────▼───────┐
                                       │  Notifier     │  email/push when a
                                       │  (worker)     │  saved search matches
                                       └───────────────┘
```

Included in this delivery: `scraper.py`, `api.py`, `requirements.txt`, and the
dashboard (`packwatch_dashboard.jsx`, delivered separately). The frontend
currently reads from an in-memory `DATA` array — point it at the API instead
by replacing that array with a `fetch('https://your-api.com/deals')` call.

## 2. Hosting options, cheapest to most robust

| Tier | Frontend | Backend + scraper | Database | Est. monthly cost |
|---|---|---|---|---|
| Weekend project | Vercel/Netlify (free) | GitHub Actions scheduled workflow runs `scraper.py`, commits a `deals.json` to the repo | Static JSON file | $0 |
| Small public site | Vercel | Render or Railway (free/hobby tier) running `api.py` + a cron job for `scraper.py` | SQLite (Render disk) or Railway Postgres | $0–15 |
| Real product, many users | Vercel/Cloudflare Pages | Render/Fly.io/AWS with a dedicated scraper worker + queue | Managed Postgres (Supabase/RDS) | $25–100+ |

Start in row 1 or 2. Only move to row 3 once you have real traffic — it's easy
to migrate later since the API contract stays the same.

## 3. Scheduling the scraper

- **GitHub Actions** (simplest, free): a `.yml` workflow with a `schedule: cron`
  trigger runs `python scraper.py` and commits the updated data.
- **Render/Railway cron jobs**: same idea, run against a persistent database
  instead of committing to git.
- Keep the interval reasonable — every 30–60 minutes is plenty for preorder
  tracking and is far gentler on the sites you're checking than continuous
  polling.

## 4. Sources: APIs first, scraping second

- **TCGPlayer** has a public Catalog + Pricing API — use this for baseline
  pricing across most TCGs rather than scraping TCGPlayer's own site.
- **eBay** has a Browse API for active listings.
- For retailers without an API (small shops, Premium Bandai, etc.), check
  `robots.txt` and the site's Terms of Service before scraping. Some
  explicitly disallow it — respect that; you can still link users to the
  product page manually or via an affiliate feed if the retailer offers one.
- Set a real `User-Agent` identifying your bot and contact info, keep request
  rates low (`REQUEST_DELAY_SECONDS` in `scraper.py`), and cache aggressively
  so you're not re-fetching the same page every cycle.
- Consider reaching out to smaller retailers directly — many will happily
  give you a product feed if you're sending them traffic.

## 5. Notifications (the "grab it first" part)

To alert users the moment a preorder opens:
1. Add a `subscriptions` table (`user_id/email`, `game`, `keyword`, `max_price`).
2. After each scrape, diff new listings against the previous run; for any
   listing whose `status` flips to `preorder_open` (or whose price drops
   below a subscriber's `max_price`), enqueue a notification.
3. Send via a transactional email provider (Resend, Postmark, SendGrid) or
   push via a service like OneSignal for a PWA/mobile app. Discord/Slack
   webhooks are a very fast, free option if your audience already lives there.

## 6. Accounts & scale (once this is a public product)

- Auth: Clerk, Auth0, or Supabase Auth — don't roll your own for a public
  product with many users.
- Move SQLite → Postgres once you have concurrent writers (the scraper) and
  many concurrent readers (site visitors).
- Add rate limiting on the API (e.g. `slowapi`) once it's public, so a single
  heavy user or bot can't overload it.
- Consider caching `/deals` responses for 1–5 minutes (Redis or even in-memory)
  since scrape frequency is already the real update cadence.

## 7. Legal / ethical notes

- Respect each retailer's Terms of Service and `robots.txt`. Scraping in
  violation of a site's ToS can get your IP or account blocked, and in some
  jurisdictions carries legal risk — when in doubt, use the official API or
  ask the retailer for a feed.
- If you monetize via affiliate links (Amazon Associates, TCGPlayer affiliate
  program, etc.), disclose that clearly to users.
- Don't misrepresent prices — always link out to the retailer for the
  purchase itself rather than processing payments yourself, at least
  initially; that also sidesteps a lot of compliance overhead.

## 8. Suggested build order

1. Get `scraper.py` + `api.py` running locally with the mock adapter (works
   out of the box).
2. Swap in one real source (TCGPlayer API is the easiest starting point).
3. Point the dashboard's `fetch()` at your local API, confirm end-to-end.
4. Deploy frontend to Vercel, backend + scraper to Render/Railway.
5. Add the notifications table + one delivery channel (start with a Discord
   webhook — it's the fastest to wire up).
6. Only then add accounts, more sources, and caching as traffic grows.
