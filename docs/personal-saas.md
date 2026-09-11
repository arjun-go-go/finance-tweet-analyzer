# Personal Product Boundary

The application is intentionally focused on personal Twitter investment
research. Shared source material is collected once; each account keeps only its
own research scope.

## User-scoped data

- Followed bloggers: `POST/DELETE/GET /api/me/bloggers`
- Tracked instruments: `POST/DELETE/GET /api/tracking`
- Alerts generated from those formal follow relationships

Bloggers, tweets, media, extracted claims, market views and prediction
verification are shared market data. User relationships point to those shared
rows instead of duplicating content.

## Product surfaces

- `/`: chronological tweet activity with per-instrument claims and macro views
- `/sources`: blogger discovery, following and collection control
- `/watch`: verified instrument directory and the user's tracked instruments
- `/settings`: account, research scope and alert entry points

The retired conversational assistant, private documents and research-project
workspaces are not part of this focused product.
