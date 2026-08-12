# Deauville result-feedback validation

Actual top-four results were supplied by the user. This audit measures only whether those horses appeared in the model's top four; it is not a full racing accuracy metric.

| Race | Actual top 4 | Updated model top 4 | Overlap | Winner class rank |
|---|---|---|---:|---:|
| R1 | 5-8-3-1 | 1-5-3-8 | 4/4 | 2 |
| R2 | 6-9-13-3 | 4-2-8-9 | 1/4 | 5 |
| R3 | 8-4-12-5 | 6-1-4-5 | 2/4 | 9 |
| R4 | 3-9-11-10 | 5-10-3-9 | 3/4 | 3 |
| R5 | 7-3-1-2 | 2-4-5-1 | 2/4 | 8 |
| R6 | 6-2-8-1 | 3-4-9-1 | 1/4 | 5 |
| R7 | 3-7-8-2 | 6-2-3-5 | 2/4 | 3 |
| R8 | 3-10-4-7 | 3-2-4-8 | 2/4 | 1 |

**Updated model top-four overlap: 17/32.**

The previous app version had 12/32 on the same supplied result set. The improvement comes from fixing unlabelled race strength, prize-money/type proxies, scratched-runner parsing, recency/progression weights, and bounded class-only result feedback. Actual finishing order still contains many non-class factors, so this metric is used only as a tuning audit.