# Affiliate program setup — PackWatch

Do these three sign-ups yourself (they require your own name/business info,
tax details, and a payout method — not something I can do on your behalf).
Realistic timeline: 30–60 minutes of forms, then a few days to a few weeks
of approval waiting depending on the program.

## 1. Amazon Associates (covers Amazon-listed sealed product)

- Sign up: https://affiliate-program.amazon.com
- Requires: an existing site/app/social presence to link (your PackWatch
  dashboard URL is enough once it's live somewhere public — even a free
  Vercel URL works for the application).
- You'll get an **Associate/Tracking ID** that looks like `yourtag-20`.
- Commission: varies by category, typically 1–4% for toys/games/collectibles.
- Important: Amazon requires **your first qualifying sale within 180 days**
  of approval or they deactivate the account — don't apply until the
  dashboard is actually live and getting a few visitors.
- Add the required disclosure: "As an Amazon Associate I earn from
  qualifying purchases."

## 2. TCGPlayer affiliate program

- TCGPlayer runs its affiliate program through **Impact** (a third-party
  affiliate network), not a self-serve dashboard signup.
- Sign up: https://impact.com → search for "TCGPlayer" in their partner
  directory, or apply directly from TCGPlayer's affiliate info page
  (search "TCGPlayer affiliate program" — the exact URL moves periodically,
  so check current details before applying).
- You'll get a **tracking/campaign link format** once approved — typically
  a redirect URL you wrap the destination in, e.g.
  `https://tcgplayer.pxf.io/c/{campaign_id}/{redirect}?u={destination_url}`
- Commission: historically in the low single digits on completed sales.

## 3. eBay Partner Network (EPN)

- Sign up: https://partnernetwork.ebay.com
- Approval is usually fast (often same-day) since eBay's program is more
  self-serve than the others.
- You'll get a **Campaign ID (`campid`)** to append to any eBay listing URL.
- Commission: varies by category, often 1–4%, paid on completed sales only
  (not clicks).

## What to do once you have your IDs

Drop your three identifiers into `affiliate.py`'s `AFFILIATE_CONFIG` dict
(see that file — it's built to take exactly these three values). Everything
else — wrapping URLs, handling retailers you're not yet monetizing, keeping
the raw URL for anything unaffiliated — is already wired up in the scraper
and dashboard.

## Retailers not covered by these three programs

Smaller shops (Gamers Guild AZ, N4YTCG, TCG Corner, Hobbiesville, etc.) don't
have public affiliate programs. For those, either:
- Leave the link unaffiliated (still valuable to users, just not monetized), or
- Email the store directly — a lot of small TCG shops will set up a simple
  discount-code affiliate deal informally if you're sending them real buyers.
  Add any of these as flat-rate manual codes in `AFFILIATE_CONFIG["manual"]`.
