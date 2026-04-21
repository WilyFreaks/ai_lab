# Interface Counter Baseline Values

Baseline average packet rates (pps) for each inter-router link.
Rule: R1 ifOut = R2 ifIn, R2 ifOut = R1 ifIn (no packet loss in normal operation).

| # | Router1 | Interface1 | R1 ifOut | R1 ifIn | Router2 | Interface2 | R2 ifOut | R2 ifIn |
|---|---------|-----------|---------|---------|---------|-----------|---------|---------|
| 1 | R9-NCS540 | FortyGigE0/0/0/28 | 6 | 6 | R8-NCS540 | FortyGigE0/0/0/28 | 6 | 6 |
| 2 | R9-NCS540 | HundredGigE0/0/0/29 | 2825 | 1372 | R7-NCS560 | HundredGigE0/0/0/0 | 1372 | 2825 |
| 3 | R8-NCS540 | HundredGigE0/0/1/0 | 5 | 7.2 | R6-NCS560 | HundredGigE0/0/0/1 | 7.2 | 5 |
| 4 | R6-NCS560 | HundredGigE0/0/0/0 | 1340 | 2222 | R7-NCS560 | HundredGigE0/1/0/0 | 2222 | 1340 |
| 5 | R6-NCS560 | HundredGigE0/1/0/0 | 6.63 | 7.83 | R4-NCS55A2 | HundredGigE0/0/2/0 | 7.83 | 6.63 |
| 6 | R7-NCS560 | HundredGigE0/0/0/1 | 1425 | 1793 | R5-NCS55A2 | HundredGigE0/0/2/0 | 1793 | 1425 |
| 7 | R4-NCS55A2 | HundredGigE0/0/1/0/0 | 7 | 7 | R5-NCS55A2 | HundredGigE0/0/1/0/0 | 7 | 7 |
| 8 | R4-NCS55A2 | HundredGigE0/0/2/1 | 6.13 | 7.29 | R2-NCS5504 | HundredGigE0/0/0/0 | 7.29 | 6.13 |
| 9 | R5-NCS55A2 | HundredGigE0/0/2/1 | 1425 | 1793 | R3-NCS5504 | HundredGigE0/0/0/1 | 1793 | 1425 |
| 10 | R2-NCS5504 | HundredGigE0/0/0/2 | 1793 | 1321 | R3-NCS5504 | HundredGigE0/0/0/2 | 1321 | 1793 |

## Notes

- **#1 (R9↔R8 FortyGigE):** No real data available — inferred from other low-traffic links (5–8 pps range)
- **#6 (R7↔R5):** Real data is fault-affected — values inferred from neighboring links (R5↔R3 traffic flow)
- **#7 (R4↔R5):** No real data available — inferred from R4's other low-traffic interfaces
