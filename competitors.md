# Competitive Analysis: Early Warning for Lift Station Pump Failures

## Executive Summary

Early pump-failure warning for wastewater lift stations is a proven category, and the opportunity is in the part the current vendors serve least: small and mid-size utilities that need warnings they can trust. Established vendors show that SCADA data can predict pump problems. Their public materials emphasize health scores, lead-time averages and work orders. Our concept adds three things: a visible rain-versus-wear explanation on every alert, honest uncertainty with a tracked accuracy record, and two purpose-built interfaces, one for the field technician and one for the maintenance planner. It runs read-only on data a utility already collects, with no new sensors.

## Problem Background

Lift stations use pumps to move sewage toward the treatment plant. When a pump fails and nobody notices in time, the wet well fills and sewage overflows into yards, streets and creeks. The result is cleanup cost, state fines and resident complaints.

Most utilities already monitor these stations with SCADA, which logs wet well levels and pump on and off events. Threshold alarms fire after a problem has started. The early signs, such as longer pump runtimes and slower emptying of the tank, sit in data the utility already holds. Rain complicates detection because storms also lengthen runtimes. A sensitive alarm fires every time it rains, and a loose one misses real faults, so operators learn to ignore alerts.

Local records show the pattern. Between 2009 and 2012, the sewer system now owned by the City of Fishers had repeated pump, power and controller failures, with overflows toward Geist Reservoir and a state fine. In Bloomington's 30 years of public overflow records, about 83 percent of overflows were weather-related and about 7 percent were caused by equipment or power failures, the portion that can be prevented.

## Market Overview

Existing solutions fall into five groups:

- Rain-aware analytics software for wastewater utilities (StormHarvester).
- Predictive maintenance platforms that read SCADA data and generate work orders (iFactory, OxMaint).
- Pump manufacturers with built-in monitoring (Xylem Flygt).
- Large industrial and water platforms (Schneider Electric, SUEZ AQUADVANCED).
- Academic research on pump station fault detection.

## Competitor Comparison

| Competitor | What it offers | Strengths | Limits | Where our concept differs |
| --- | --- | --- | --- | --- |
| **StormHarvester** | Cloud pump station alerting that combines simple pump telemetry with rainfall data and AI analytics. Also offers inflow and infiltration detection, blockage detection and spill prediction. | Rain-aware. Issues descriptive alerts that explain the likely issue and context. Holds a long-term Northumbrian Water contract and serves Southern Water. | Publicly documented customers are UK water companies. Public materials focus on alerts rather than on showing the evidence behind each one. | Evidence panel with a raw versus rain-corrected view, soil and groundwater context, and designs for two user roles. |
| **iFactory** | Predictive maintenance that connects to existing lift station SCADA through read-only OPC-UA or Modbus and generates condition-based work orders. Describes a three-week activation sequence. | No SCADA modification required. Work order generation and compliance reporting. | Some deployments add wireless vibration and current sensors. Lead-time claims vary across its pages, from 48 to 96 hours to 14 to 90 days, and are stated as averages rather than per-alert evidence. Sales process centers on demos. | Sensor-free by design, per-alert ranges with confidence levels, and a published false-alarm record. |
| **OxMaint** | Lift station predictive maintenance with pump health scoring, connected to maintenance records and compliance tracking. | Reads existing SCADA level and motor data. Links alerts to work orders. | Adds vibration and current monitoring at the pump unit level, which means new hardware for full capability. Performance figures come from vendor marketing. | Stays read-only and makes rain correction the central feature. |
| **Xylem (Flygt)** | Pump monitoring integrated with its pumps and controllers. One system records pump starts and stops, vibration, power quality, energy use, and bearing and seal temperatures. | Deep hardware knowledge and detailed condition data. | Tied to Xylem equipment. A utility with mixed pump brands cannot cover its whole fleet. | Vendor-neutral. Works on any station that exports wet well level and pump status. |
| **Schneider Electric** | Research on pump station health assessment using time series anomaly detection at the industrial edge. Connects to the same registers as the existing SCADA, so no new sensors are needed. | Uses weather and time of day as context. Strong industrial engineering. | Edge deployment suits larger operators. The source is a research paper, not a packaged product for small utilities. | Simple file-based onboarding for utilities without IT or controls staff. |
| **SUEZ AQUADVANCED** | Platform that combines monitoring, forecasting and anomaly detection and gives operators recommendations. | Broad capability and recommendations instead of raw numbers. | Scoped for large utilities and full platform adoption. | Lightweight entry point for utilities too small for a platform rollout. |
| **Academic research (KTH)** | Physics-enhanced fault detection for wastewater pump stations, with a simulator compared against high-frequency municipal SCADA data. | Supports the physics-based approach to separating faults from normal variation. | A research method, not an operator tool. | Applies the same physical reasoning in a usable product with technician and planner interfaces. |

## Market Gaps and Our Response

| Gap | Our response |
| --- | --- |
| Alerts are presented as scores or messages, and the proof behind each one is limited. | An evidence panel on every alert, including a toggle between raw and rain-corrected pump capacity. |
| Lead times are reported as averages across a fleet. | Each alert shows a range, such as 4 to 9 days, with a confidence level and "inspect" wording rather than a failure prediction. |
| Field findings are not shown improving the model. | "Found issue" and "Checked, OK" responses from technicians feed a visible accuracy record. |
| Stations are ranked by pump health alone. | Ranking by health and consequence, using terrain to show where an overflow would flow, such as toward a creek or reservoir. |
| Rainfall is the main environmental input. | Soil moisture and groundwater or creek levels added as further non-pump explanations for high runtime. |
| Onboarding involves demos, edge servers or sensor installs. | Upload a SCADA historian export and get results without installing anything. |
| A single interface serves all users. | A phone view for the technician with one decision per alert, and a desktop view for the planner with fleet context and scheduling. |

## How the Concept Separates Rain from Wear

When a pump is off, the rise in wet well level gives the inflow rate. When the pump is on, pump capacity equals the drawdown rate plus the inflow rate. Capacity stays stable in dry and stormy weather, so a downward trend over several days points to wear or clogging rather than rain. Projecting the trend forward gives an estimate of the days remaining before the pump crosses a failure threshold. Each pump pair also acts as a comparison: two pumps at one station see the same inflow, so a gap between them is a strong signal.

## Positioning

**Target users.** Operators and maintenance planners at small and mid-size utilities who have SCADA data but not the staff to analyze it.

**Value statement.** Utilities already collect the data that predicts pump failures. We turn it into early, trustworthy warnings.

**Safety position.** The tool is read-only. It has no access to control systems and issues no control commands. It recommends inspection, and the people who run the system make the decisions.

## Scope and Validation

This analysis draws on public vendor materials, press coverage and published research. Vendor performance figures are self-reported and have not been independently verified. Initial evaluation of the concept uses simulated station data with injected faults. The next step is validation on a historian export from a real utility, along with interviews with operators and planners to confirm which alerts they would act on.

## Sources

- Smart Water Magazine, StormHarvester at Southern Water: https://smartwatermagazine.com/news/stormharvester/turning-alarm-flood-actionable-alerts-southern-waters-ai-pump-monitoring
- Irish News, StormHarvester and Northumbrian Water: https://ie.irishnews.com/news/business/belfast-tech-firm-stormharvester-wins-long-term-northumbrian-water-contract-FXFB5SBOCBHJJAJGXVISDEXK5Q
- CB Insights, StormHarvester profile: https://www.cbinsights.com/company/stormharvester
- iFactory, lift station and pump station monitoring: https://ifactoryapp.com/industries/infrastructure-management/lift-station-pump-station-maintenance-ai-wet-well-monitoring
- iFactory, pump station analytics: https://ifactoryapp.com/industries/government/pump-station-analytics-water-wastewater
- OxMaint, lift station predictive maintenance: https://oxmaint.com/industries/government/wastewater-lift-station-predictive-maintenance-system
- Xylem, Fairwood Lift Station case study: https://www.xylem.com/en-kw/making-waves/water-utilities-news/lift-station-overflows-solved-with-xylem-solution/
- PHM Society, Health Assessment of Pump Stations using Time Series Anomaly Detection (Schneider Electric): https://papers.phmsociety.org/index.php/phmconf/article/view/3870
- CB Insights, SUEZ AQUADVANCED mention: https://www.cbinsights.com/company/sewerai
- arXiv, Modeling and Physics-Enhanced Fault Detection in Wastewater Pump Stations: https://arxiv.org/pdf/2511.11304.pdf
