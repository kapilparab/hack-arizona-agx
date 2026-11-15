# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Pest Control Advisers (PCAs) and farmers in the Yuma, Arizona vegetable and citrus valley. The primary scene is pre-dawn (around 05:00), on a phone in a pickup cab before leaving for the fields: they check which job runs next, when to depart, and whether anything blocks it. Later the same morning they may glance at it again in full desert sun. Desktop planning use is secondary.

## Product Purpose

CanopyGuard plans spray windows. The treatment is already decided by pest scouting or a spray schedule. CanopyGuard answers: given the target date, available equipment, local weather and neighboring fields, what is the earliest suitable opportunity to complete this job? Success is a crew leaving at the right time, for the right field, without spraying into a temperature inversion.

## Positioning

Paired-height sensing (5 ft and 30 ft) catches surface inversions that a single ground station would miss ("a 5 ft station alone would say Go"), and a sequence planner reorders jobs so deadlines are met inside real weather windows.

## Operating Context

- Four views: Today (home), Field map, Schedule, Records.
- Scenario clock in MST (America/Phoenix). Hackathon demo (Hack Arizona AgX) driven by a three-minute script in README.md.
- English, with Spanish for explanations and status labels.

## Capabilities and Constraints

- Decision support only. It does not diagnose pests, choose pesticides, recommend rates, predict drift, or control equipment. "Go" means no configured flags were detected, not guaranteed safety.
- Statuses: Go, Caution, Stop, Insufficient data. Missing or stale data is never Go.
- All fields, growers, sensors, neighbors and product constraints are fictional or simulated and must stay labeled that way.

## Evidence on Hand

- Crop and equipment photos from Wikimedia Commons with credits in `app/photo_credits.json`.
- No real customers, testimonials, field validation or verified manufacturer droplet tables. Do not fabricate any.

## Product Principles

1. The next action comes first: what runs next, when to leave, what blocks it.
2. Uncertainty is shown, never hidden: simulated, interpolated, unverified and insufficient states stay visible.
3. Explain every Stop in plain terms with its cause.
4. Usable one-handed on a phone in a dim cab and in direct sun.

## Accessibility & Inclusion

Status must never rely on color alone (icons and words accompany it). Readable at low screen brightness and in direct sunlight. Respect reduced motion.
