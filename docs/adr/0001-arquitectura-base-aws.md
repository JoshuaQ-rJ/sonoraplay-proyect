# ADR-0001 · Arquitectura base en AWS: servicios 24/7 al menor costo justificable

| Campo | Valor |
|---|---|
| Estado | Propuesto (se acepta en la review del Sprint 1) |
| Fecha | 2026-09-30 |
| Historia que lo origina | HU 07 · EG-16 |
| Responsable | Joshua (lidera) · María Clara · Andrea |
| Revisó | Pendiente |
| Referencias | E-01 v1, temas 5–10 y 16, RNF-01, RNF-04, CT-02 |

## 1. Contexto

SonoraPlay necesita una plataforma en AWS que reciba eventos sin perderlos, los procese con Spark, liquide el día 3 en menos de 1 hora y exponga una API a los sellos. El equipo acordó que **la plataforma queda encendida durante todo el proyecto**, no solo en la demo. El enunciado pide el **menor costo justificable** y cubrir los 20 temas del programa.

Como referencia se revisó una arquitectura web genérica de AWS (ELB + EC2 con Auto Scaling + RDS + Memcache + DynamoDB + SES + S3).

## 2. Qué debe cumplir la decisión

- **Temas obligatorios:** VPC y EC2 (6), S3 y RDS (7), ECR y ECS (8), Fargate y ALB (9), RabbitMQ (10), Airflow con Celery (11–12), Spark en Fargate (16) y EKS (19).
- **RNF-04:** cero eventos perdidos.
- **RNF-01:** liquidación en menos de 1 hora.
- **RN-11 / CA-08:** cada sello ve solo lo suyo.
- **Costo:** los servicios 24/7 pagan todas las horas, así que el precio por hora pesa más que el precio por uso.
- **Penalizaciones:** credenciales expuestas (−15%) e infraestructura sin destruir (−10%).

## 3. Opciones consideradas

| Opción | A favor | En contra | USD/mes aprox. |
|---|---|---|---|
| A · Todo en una EC2 con docker compose | La más barata | No cubre los temas 7–9 ni la separación de capas; un punto único de falla | 30–40 |
| B · Stack "administrado" (NAT Gateway, Amazon MQ, MWAA, Fargate On-Demand para todo) | Menos mantenimiento | MWAA y Amazon MQ multiplican el costo 24/7 | > 450 |
| C · **Híbrido:** Fargate para servicios, EC2 pequeñas para RabbitMQ y Airflow, instancia NAT, Spot donde se tolera interrupción, ARM64 | Cubre todos los temas a bajo costo | Más mantenimiento en las EC2; la instancia NAT es un punto único de falla | ≈ 115–120 |

## 4. Decisión

**Elegimos la opción C**, detallada en [arquitectura-v1.md](../arquitectura/arquitectura-v1.md). Es la más barata que cumple todos los temas y los requisitos RNF-01 y RNF-04. De la arquitectura de referencia se mantienen el ALB, RDS con backups, S3 y las notificaciones (Budgets + SNS). Se reemplaza EC2 con Auto Scaling por ECS Fargate. Se descartan DynamoDB, Memcache y SES porque ninguna regla ni requisito los justifica.

## 5. Consecuencias

- **Positivas:** plataforma disponible 24/7 por unos 115–120 USD al mes; todos los temas tienen un lugar natural; solo el ALB es público.
- **Negativas:** el equipo mantiene dos EC2 (RabbitMQ y Airflow). RDS es Single-AZ.
- **Riesgos:** las interrupciones de Spot se mitigan con ACK manual y reintentos de Airflow. Si la NAT cae, solo se afecta F6/F7, y hay alarma con recuperación automática. EKS se enciende solo en el Sprint 5 y la demo.
- **Decisiones que se derivan:** ADR-0009 a ADR-0019 del [registro](README.md).

## 6. Cómo sabremos que funciona

- `terraform apply` levanta todo y `terraform destroy` lo elimina sin residuos (HU 17 y 38).
- El costo real de la primera semana en AWS queda dentro de ±20% del estimado (HU 23).
- La API responde por la URL del ALB y sus logs aparecen en CloudWatch (HU 18).

## 7. Fuentes

- AWS Well-Architected Framework, pilar de optimización de costos: https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html
- Precios de AWS Fargate (incluye Spot y ARM): https://aws.amazon.com/fargate/pricing/
- Precios de Amazon VPC (NAT Gateway, IPv4 públicas): https://aws.amazon.com/vpc/pricing/
- Precios de Amazon MQ: https://aws.amazon.com/amazon-mq/pricing/
- Precios de Amazon MWAA: https://aws.amazon.com/managed-workflows-for-apache-airflow/pricing/
