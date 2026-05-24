# Error Analysis

## biollm
- Scenarios attempted: 200
- Wrong / incomplete:  144  (72.0%)

| Failure mode | Count | % of failures |
|--------------|------:|--------------:|
| clock_confusion | 49 | 34.0% |
| direction_over | 53 | 36.8% |
| direction_under | 16 | 11.1% |
| missed_discordance | 11 | 7.6% |
| hallucinated_discordance | 26 | 18.1% |
| confounder_blind | 9 | 6.2% |
| hallucinated_intervention | 42 | 29.2% |
| error_or_parse_fail | 16 | 11.1% |
| other | 15 | 10.4% |

## claude
- Scenarios attempted: 200
- Wrong / incomplete:  92  (46.0%)

| Failure mode | Count | % of failures |
|--------------|------:|--------------:|
| clock_confusion | 5 | 5.4% |
| direction_over | 5 | 5.4% |
| direction_under | 3 | 3.3% |
| missed_discordance | 2 | 2.2% |
| hallucinated_discordance | 22 | 23.9% |
| hallucinated_intervention | 49 | 53.3% |
| other | 25 | 27.2% |
