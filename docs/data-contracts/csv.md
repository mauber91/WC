# CSV contracts

All timestamps are ISO-8601 UTC. Team references use three-letter FIFA codes. `selection` for 1X2 markets is one of `team_a`, `draw`, or `team_b`.

| Dataset | Required columns |
| --- | --- |
| `teams` | `fifa_code,name,country_code,confederation` |
| `draw` | `fifa_code,name,country_code,confederation,group_code,draw_position,is_host` |
| `fixtures` | `match_number,group_code,team_a_fifa_code,team_b_fifa_code,scheduled_at` |
| `results` | `match_number,team_a_goals_90,team_b_goals_90` |
| `ratings` | `fifa_code,rating_type,rating_value,effective_at,source` |
| `bookmaker_odds` | `match_number,bookmaker,selection,decimal_odds,snapshot_at` |
| `prediction_markets` | `platform,external_market_id,contract_id,market_type,selection,yes_price,snapshot_at` |

Bundled seed files under `data/seed/` follow the same contracts: `draw.csv`, `fixtures.csv`, `results.csv`, `ratings.csv`, `bookmaker_odds.csv`, `prediction_markets.csv`, plus `standings_snapshot_june20.json` for golden tests. Regenerate with `make seed-data`.

For exact tiebreaks, result files should also include yellow, indirect-red, direct-red, and yellow-plus-direct-red totals for both teams. Missing conduct data marks affected output provisional.
