High impact (worth doing before sharing links)
1. Meta description

<meta name="description" content="Monte Carlo forecasts, knockout bracket projections, and match probabilities for FIFA World Cup 2026." />
This shows up in Google snippets and some chat apps.

2. Open Graph + Twitter Card tags

Crawlers (iMessage, Slack, X, Facebook, LinkedIn) read these, not the page title alone:

og:title, og:description, og:url, og:type, og:site_name
twitter:card (summary_large_image)
twitter:title, twitter:description, twitter:image
3. A real share image (og:image)

This is the biggest gap. The ⚽ favicon won’t produce a good preview card. You want a 1200×630 PNG (or JPG) — e.g. green brand background, “WC Knockout Predictor”, maybe a bracket silhouette or flag strip. Without it, shared links look bare or pull a random screenshot.

4. Canonical URL

<link rel="canonical" href="https://wc-forecast.pages.dev/" />
Use your real production URL (custom domain if you have one). A VITE_SITE_URL build env var keeps this correct across environments.

Medium impact
Item	Why
theme-color (#153d2b)
Browser chrome matches your brand on mobile
robots.txt
Allow: / for the public site
Brand alignment
Sidebar says “Forecast”; tab title says “WC Knockout Predictor” — pick one name and use it everywhere
apple-touch-icon
Better home-screen icon than the emoji SVG
Lower priority (but nice for a data product)
Per-route meta (react-helmet-async) so /teams/argentina gets its own title/description when shared
sitemap.xml for /bracket, /teams, /methodology, etc.
JSON-LD (WebApplication or WebSite schema) for richer search results
noindex on local/dev builds if they’re ever reachable on the public internet (published mode only should be indexed)
What you probably don’t need yet
Heavy SEO tooling or a blog
Per-match OG images (high effort, marginal return unless you’re actively sharing individual fixtures)
A web app manifest unless you want “Add to Home Screen”
Suggested copy (if you want consistency)
Field	Suggestion
Title
WC Knockout Predictor
Description
Monte Carlo knockout forecasts, live bracket projections, and calibrated match probabilities for FIFA World Cup 2026.
og:site_name
WC Knockout Predictor
Sidebar brand
Rename “Forecast” → “WC Knockout Predictor” (or shorten to “Knockout Predictor”)
Bottom line: add description + OG/Twitter tags + a proper og-image.png + canonical URL. That’s the minimum for links to look good when shared. Everything else is polish.

