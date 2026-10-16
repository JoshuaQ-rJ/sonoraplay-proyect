# ADR-0020 — AWS off by default: test windows in Sprints 3–5 and continuous operation only in the final week

> Complete English translation of [the Spanish decision record](../0020-ventanas-encendido-aws.md). Cost figures are estimates, not observed AWS charges.

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-09 |
| Originating story | HU 07 · EG-16 (architecture v1 correction) |
| Owners | María Clara (proposer), Joshua, Andrea |
| Reviewed by | Andrea — approved in PR #14 (merged 2026-10-09) |
| References | [ADR-0001](0001-aws-base-architecture.md), [architecture v1.2](../../arquitectura/arquitectura-v1.md), HU 17 (EG-26), HU 23 (EG-32), HU 32 (EG-41), HU 38; −10% penalty for failure to destroy infrastructure |

## 1. Context

ADR-0001 selected the hybrid option C but originally described it as **running throughout the project**. That contradicts the team's agreed approach: provision and destroy infrastructure using Terraform, run it only during short test windows, and keep it continuously running only in the final week until the demo.

Option C costs an estimated USD 115–120 per month when continuously running. Keeping it on for all six project weeks would cost approximately USD 165–170 excluding EKS, much of it for unused hours.

This decision **does not change the services** selected in ADR-0001 or architecture v1; it only specifies when they are running.

## 2. Decision criteria

- **Cost:** meet the assignment's lowest-justifiable-cost requirement.
- **Requirement:** HU 17 / HU 38, reproducible `terraform apply` and `terraform destroy` without residual resources.
- **Requirement:** HU 23, actual costs within ±20% of estimates.
- **Penalty:** −10% if infrastructure is not destroyed after the demo.
- **Business:** the day-3 settlement (RF-04, RNF-01) must be demonstrable.
- **Data:** removing RDS between windows must not cause irrecoverable data loss.

## 3. Options considered

| Option | Advantages | Disadvantages | Approx. USD for entire project |
|---|---|---|---:|
| A · Always on for six weeks | No recreation; RDS retains data and backups | Pays for unused weeks; a forgotten final destroy keeps generating charges | ≈165–170 + EKS |
| B · **Off by default**, short windows in S3–S5, continuously on in S6 | Pays for tests and demo week; rehearses apply/destroy every window | Requires reseeding RDS each window; day-3 processing demonstrated using a logical date | ≈30–40 + EKS |
| C · Only on for demo day | Cheapest | Insufficient time to fix AWS-only failures; HU 23 lacks a real week of costs to measure | ≈5–10 + EKS |

## 4. Decision

**Option B was selected.** It is the least expensive option allowing `apply`/`destroy` tests before the demo (HU 17, HU 38), measurement of a real operating week (HU 23), and a demonstration of day-3 settlement (RF-04).

1. By default the environment is **destroyed**. Between windows only nearly zero-cost resources remain: Terraform state bucket, ECR, SSM Parameter Store, Budgets, and CloudTrail bucket.
2. Each test window follows `terraform apply` → tests → `terraform destroy` **on the same day**.
3. During Sprint 6 the environment stays on until the demo and is then destroyed, with evidence.
4. EKS is enabled only for its Sprint 5 test and the demo (ADR-0018 in the [register](../README.md)).
5. RDS is recreated and populated with reproducible seeds each window (EG-13 / EG-28). S3 may remain because storage costs pennies.
6. The day-3 DAG is manually triggered using `airflow dags trigger --logical-date`.
7. In the architecture, **“24/7”** means “active while the environment is running.”

## 5. Consequences

- **Positive:** project cost falls to an estimated USD 30–40 excluding EKS. Every window rehearses provisioning and destruction, so final teardown is not attempted for the first time on demo day.
- **Trade-offs:** RDS must be reseeded for each window; day-3 processing uses a logical date; automated RDS backups last only as long as the test window.
- **Risks and mitigations:** forgetting `destroy` → AWS Budgets alert through SNS; manually created resources outside Terraform → team rule prohibits them; AWS-specific failures found late → Sprint 3–5 windows provide earlier opportunities to detect them.

## 6. How to verify

- Every test window has evidence of both `terraform apply` and `terraform destroy`.
- Actual final-week spending is within ±20% of the Cost Explorer estimate (HU 23).
- Outside test windows, daily Cost Explorer cost is approximately USD 0.

These are acceptance checks, **not verified deployment or billing evidence**.

## 7. Sources

- AWS Well-Architected cost optimization: https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html
- Terraform destroy: https://developer.hashicorp.com/terraform/cli/commands/destroy
- Apache Airflow CLI: https://airflow.apache.org/docs/apache-airflow/stable/cli-and-env-variables-ref.html#trigger
- [ADR-0001](0001-aws-base-architecture.md) and [architecture v1](../../arquitectura/arquitectura-v1.md).
