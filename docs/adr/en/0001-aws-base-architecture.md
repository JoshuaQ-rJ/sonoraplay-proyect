# ADR-0001 — Base AWS architecture: 24/7 services at the lowest justifiable cost

> Complete English translation of [the Spanish decision record](../0001-arquitectura-base-aws.md). Operating hours are amended by ADR-0020. This is a design decision, not evidence of an AWS deployment.

| Field | Value |
|---|---|
| Status | Accepted; operating hours amended by [ADR-0020](0020-aws-operating-windows.md) |
| Date | 2026-09-30 |
| Originating story | HU 07 · EG-16 |
| Owners | Joshua (lead), María Clara, Andrea |
| Reviewed by | Andrea — approved 2026-10-02 |
| References | E-01 v1, topics 5–10 and 16, RNF-01, RNF-04, CT-02 |

## 1. Context

SonoraPlay needs an AWS platform that receives events without losing them, processes them with Spark, completes settlement on day 3 in less than one hour, and exposes a rights-holder API. Services described as always-on are active **only while the environment is running**; ADR-0020 defines when it runs. The assignment requires the **lowest justifiable cost** and coverage of all 20 curriculum topics.

The team reviewed a generic AWS web reference architecture (ELB + EC2 Auto Scaling + RDS + Memcache + DynamoDB + SES + S3).

## 2. Decision criteria

- **Mandatory topics:** VPC and EC2 (6); S3 and RDS (7); ECR and ECS (8); Fargate and ALB (9); RabbitMQ (10); Airflow with Celery (11–12); Spark on Fargate (16); and EKS (19).
- **RNF-04:** no lost events.
- **RNF-01:** settlement in under one hour.
- **RN-11 / CA-08:** each rights holder sees only its own data.
- **Cost:** always-on services incur hourly charges while the environment runs, so hourly pricing matters more than usage pricing.
- **Penalties:** exposed credentials (−15%) and infrastructure not destroyed (−10%).

## 3. Options considered

| Option | Advantages | Disadvantages | Approx. USD/month |
|---|---|---|---:|
| A · Everything on one EC2 with Docker Compose | Lowest cost | Does not cover topics 7–9 or layer separation; single point of failure | 30–40 |
| B · Managed stack (NAT Gateway, Amazon MQ, MWAA, Fargate On-Demand everywhere) | Less maintenance | MWAA and Amazon MQ greatly increase hourly costs | >450 |
| C · **Hybrid:** Fargate services, small EC2 for RabbitMQ and Airflow, NAT instance, Spot where interruption is tolerable, ARM64 | Covers the topics at lower cost | More EC2 maintenance; NAT instance is a single point of failure | ≈115–120 |

## 4. Decision

**Option C was selected**, as detailed in [architecture v1](../../arquitectura/arquitectura-v1.md). It is the least expensive option meeting the required topics and RNF-01/RNF-04. ALB, RDS backups, S3, and Budgets + SNS notifications remain from the reference architecture. ECS Fargate replaces EC2 Auto Scaling. DynamoDB, Memcache, and SES are excluded because no business rule or requirement justifies them.

## 5. Consequences

- **Positive:** with all services running, the estimate is ≈ USD 115–120/month (≈ USD 27/week); under ADR-0020 the project estimate is ≈ USD 30–40 excluding EKS. Each topic has a defined role and only the ALB is public.
- **Negative:** the team operates two EC2 instances (RabbitMQ and Airflow). RDS is Single-AZ.
- **Risks:** Spot interruptions are mitigated with manual ACK and Airflow retries. NAT failure interrupts F6/F7, ECR downloads, CloudWatch logs, and SSM; S3 traffic continues through its endpoint. An automatic-recovery alarm is specified in architecture v1.1 section 8. EKS runs only during its Sprint 5 test and the demo (ADR-0020).
- **Related decisions:** ADR-0009 through ADR-0019 in the [ADR register](../README.md), and ADR-0020 on operating hours.
- **Revision 1.1 (2026-10-05):** added CloudTrail, ACM, Cloud Map, Internet Gateway, and Security Groups without changing option C, for an estimated ≈ USD 1/month more.

## 6. How to verify

- `terraform apply` provisions the environment and `terraform destroy` removes it without residual resources (HU 17 and HU 38).
- Actual AWS spending in the first week is within ±20% of the estimate (HU 23).
- The API responds through the ALB URL and its logs appear in CloudWatch (HU 18).

These are **verification criteria**, not claims that the tests or deployment have occurred.

## 7. Sources

- AWS Well-Architected cost optimization: https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html
- AWS Fargate pricing: https://aws.amazon.com/fargate/pricing/
- Amazon VPC pricing: https://aws.amazon.com/vpc/pricing/
- Amazon MQ pricing: https://aws.amazon.com/amazon-mq/pricing/
- Amazon MWAA pricing: https://aws.amazon.com/managed-workflows-for-apache-airflow/pricing/
