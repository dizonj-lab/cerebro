# Route Planner Outage Postmortem

Presented by Daniel Reyes, CTO

Larkspur Logistics · 19 July 2024

## Summary

On 17 July 2024 Harbor's route planner stopped assigning tasks for 47 minutes across six customer sites. Wren robots finished their current picks and then waited safely. No one was hurt and no orders were lost, but about 9,000 picks were delayed.

## Cause

A database migration added an index during peak hours and locked the task table. The planner's health check only tested that the service answered, not that it could write tasks, so the alert came 31 minutes late.

## What we changed

Migrations now run outside peak hours and are tested against a copy of production data. The health check now writes and reads a test task. Customers receive a status page link within ten minutes of any incident, as the information security policy requires.
