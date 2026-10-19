# Game Sentinel: Kinguin data update

Only the feed converter and publication workflow belong in this repository. It does not contain the Android source, APKs, account passwords or Cloudflare tokens.

The GitHub Actions workflow runs every three hours (minute 17) or manually. It tests the converter, streams the partner XML into a temporary SQLite database, creates 4096 small JSON blocks, verifies all blocks and then publishes one complete Cloudflare Pages deployment. Failed conversions do not publish; the previous deployment stays live. Scheduled execution may be delayed by GitHub.

Cloudflare project: `game-sentinel-kinguin-data`.

Required repository Actions secrets:

- `CLOUDFLARE_ACCOUNT_ID`: the selected account identifier.
- `CLOUDFLARE_API_TOKEN`: a token authorized for Cloudflare Pages Edit on the selected account. Never commit its value to a file.

The feed URL is public and already contains multiple currencies. Prices are kept as provided. Shipping/additional-cost data and region limitations remain separate; no currency conversion or country-activation assumption is performed. Steam product variants remain separate. Android matching and referral links are configured independently.

Tests: `python3 -m unittest discover -p test_convert_feed.py`.

Cloudflare serves static JSON only; no Functions are used. The workflow writes no dataset back to GitHub and stores no large artifact. For a public repository, use only standard runners to retain free GitHub Actions execution. Do not enable paid add-ons.
