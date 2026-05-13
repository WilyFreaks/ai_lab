<pre><code># 5G WDM Backbone Network Failure Detection & Root Cause Analysis

## Overview
This skill guides the complete workflow from detection of network quality degradation in a 5G WDM backbone environment to root cause identification and recovery guidance.

Using Splunk episode correlation analysis, it performs cross-domain analysis across ThousandEyes, TWAMP, Telemetry, ios, and syslog data sources to identify the failure point, determine the impacted scope, and isolate the device suspected to be causing the issue.

## Network Topology
```text
R8 -- R6 -- R4 -- R2
|     |           |
R9 -- R7 -- R5 -- R3
```

- Routers: R2–R9 (Cisco NCS Series)
- Protocols: SR-MPLS, IS-IS, BFD, BGP
- Management IPs: 172.20.0.{2-9} = R{2-9}
- Services: Traffic engineering controlled by SR-TE Policy per VRF slice (Slice 1001–1004)

## Execution Flow
Proceed through the following steps. At the beginning of each step, always display the following status format:

```text
* Step X Running: [Brief description of the current action]
```
Before infer the SPL to run for the investigation, check available saved searches to meet your needs. Read the desciption of the saved searches to understand the function and the parameters if it's available. If the description is not avilable, use saved search names to determine the use. 
All the necessary saved searches are in ai_lab app. Don't run any saved searches outside of ai_lab.

At the completion of each step, output a summary of the findings and indicate the next step.

## Step 1: ThousandEyes Monitoring

Always display at the beginning:

```text
* Step 1 Running: Checking the service monitor status for the last 60 minutes using ThousandEyes...
```

Execute the ThousandEyes SPL query over the last 60 minutes.

If avg(response_time_sec) exceeds upper_bound, the service is considered degraded.

The timestamp when the anomaly is detected should be treated as the failure detection time.

## Step 2: Episode Correlation Analysis

Always display at the beginning:

```text
* Step 2 Running: Checking alert activity using Splunk Episode Correlation Analysis...
```

Retrieve the episode list using the Splunk saved search and verify alert activity.

An episode is escalated to Critical when an Interface Counter Mismatch is detected. This is considered deterministic evidence of a data plane level failure.

Do not speculate on the root cause until it is validated through syslog correlation analysis.

## Step 3: TWAMP Quality Analysis

Always display at the beginning:

```text
* Step 3 Running: Measuring packet loss and latency on impacted slices using TWAMP data...
```

Analyze packet loss, latency, and jitter per slice using PCA TWAMP data.

## Step 4: Path Mapping

Always display at the beginning:

```text
* Step 4 Running: Comparing degraded and healthy slices to identify the problematic node...
```

Identify slices with high packet loss, latency, and jitter, then isolate network nodes that only exist in degraded slice paths.

## Step 5: Telemetry Interface Verification

Always display at the beginning:

```text
* Step 5 Running: Verifying detailed interface information on suspected routers using Telemetry data...
```

Identify router interfaces with greater than 30% packet loss.

## Step 6: Router ios Event Analysis

Always display at the beginning:

```text
* Step 6 Running: Reviewing router ios logs to identify network-related events...
```

Correlate BFD down, IS-IS adjacency loss, and SR-TE Policy DOWN events with TWAMP quality degradation.

Verify how SR-TE policies changed due to the failure.

## Step 7: WDM syslog Analysis

Always display at the beginning:

```text
* Step 7 Running: Reviewing WDM syslog events for transponder-side issues per router...
```

Use Splunk saved searches to identify WDM transponder abnormalities connected to the affected routers.

Available saved searches:

- wdm_LSBIASCUR_over_time_by_router  
  High values may indicate transponder degradation on the Tx side.

- wdm_FEC_BEF_COR_ER_over_time_by_router  
  High values may indicate degradation on the Tx-side transponder or optical fiber.

- wdm_LOSTOPCUR_over_time_by_router  
  High lost_opcur values may indicate degradation on the Tx-side transponder or optical fiber.

- wdm_BDTEMPCUR_over_time_by_router  
  High values may indicate transponder board failure.

- wdm_EDTMPCUR_over_time_by_router  
  High values may indicate EDFA failure within the transponder equipment.

## Root Cause Identification, Recommended Actions, and Service Recovery Validation

Use the saved searches above to verify the status of WDM transponders connected to the suspected routers identified through Step 6 and infer the root cause.

Based on the inferred root cause, recommend the appropriate remediation actions.

Finally, verify the ThousandEyes service monitor status from Step 1 again and confirm that the network service has successfully recovered after the SR-TE policy switchover.</code></pre>
