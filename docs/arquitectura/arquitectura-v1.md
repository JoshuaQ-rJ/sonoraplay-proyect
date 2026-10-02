# Arquitectura v1 · SonoraPlay Regalías

> Entregable **E-01 v1** · Tarea **07 (EG-16)** · Sprint 1 · Épica EP-9
> Responsables: los tres (lidera Joshua) · Estado: **Propuesta para revisión del equipo**
> Decisión formal: [ADR-0001](../adr/0001-arquitectura-base-aws.md)

![Arquitectura v1](sonoraplay-arquitectura-v1.png)

Fuente editable: `sonoraplay-arquitectura-v1.drawio` (abrir en [diagrams.net](https://app.diagrams.net) o con la extensión Draw.io de VS Code).

## 1. Principios de diseño

1. **Servicios 24/7, lotes bajo demanda.** Todo lo que atiende peticiones o recibe eventos queda encendido (API, RabbitMQ, Airflow, RDS). Spark no es un servicio: Airflow lo lanza, corre y se apaga. Está desplegado siempre, pero solo se paga mientras procesa.
2. **Menor costo justificable.** Cada servicio se elige como la opción más barata que cumple un tema obligatorio, una regla de negocio (RN), un requisito (RF/RNF) o un criterio de aceptación (CA).
3. **Nada público salvo el ALB.** Cómputo y datos van en subredes privadas. El equipo entra por SSM Session Manager, sin bastión ni puertos abiertos.
4. **Cero secretos en el código.** Los secretos van en SSM Parameter Store y GitHub entra a AWS con OIDC. Una credencial expuesta cuesta −15%.
5. **Todo se crea y se destruye con Terraform.** No destruir la infraestructura tras la demo cuesta −10%.

## 2. Servicios elegidos

| Capa | Servicio | Tamaño / modo | Estado | Por qué | Trazabilidad |
|---|---|---|---|---|---|
| Red | VPC con 2 AZ, subredes públicas y privadas | 10.0.0.0/16 | 24/7 | Aislamiento; el ALB y el grupo de subredes de RDS exigen 2 AZ | Tema 6 · HU 17 |
| Salida | Instancia NAT | EC2 t4g.nano | 24/7 | ~90% más barata que un NAT Gateway; se usa para F6/F7 y actualizaciones | Tema 6 · ADR-0010 |
| Salida a S3 | Endpoint Gateway de S3 | — | 24/7 | Gratis; el tráfico a S3 no pasa por la NAT | Tema 7 |
| Entrada | Application Load Balancer | 1 ALB, HTTPS | 24/7 | Health checks y punto único de entrada | Tema 9 · HU 18 |
| API de titulares | ECS Fargate On-Demand, ARM64 | 0,25 vCPU / 0,5 GB | 24/7 | Sin servidores que administrar; On-Demand porque atiende a los sellos | RF-05, RN-11, CA-08 · HU 12, 18 |
| API de contratos F4 | ECS Fargate On-Demand, ARM64 | 0,25 vCPU / 0,5 GB | 24/7 | La consulta Spark para el % vigente | F4, RN-07 · HU 11 |
| Simulador F2 | ECS Fargate **Spot** | 0,25 vCPU / 0,5 GB | 24/7 | Hasta ~70% más barato; si AWS lo interrumpe, se reinicia | F2, CT-06 · HU 10 |
| Consumidor → Bronze | ECS Fargate **Spot** | 0,25 vCPU / 0,5 GB | 24/7 | Con ACK manual, el mensaje sin confirmar vuelve a la cola: la interrupción no pierde datos | RF-01, RNF-04 · HU 20, 24 |
| Mensajería | RabbitMQ en EC2 | t4g.small | 24/7 | Más barato que Amazon MQ; también es el broker de Celery | Tema 10 · ADR-0013 |
| Orquestación | Airflow (CeleryExecutor) en EC2 con docker compose | t4g.medium | 24/7 | MWAA cuesta cientos de USD al mes | Temas 11–12 · ADR-0015 |
| Procesamiento | Spark en tareas ECS Fargate **Spot** | 2 vCPU / 8 GB por job | Bajo demanda | Solo se paga mientras corre; Airflow reintenta si se interrumpe | Temas 13–16 · RNF-01 |
| Data Lake | Amazon S3 Bronze / Silver / Gold | Parquet por año/mes/país | Siempre | Barato y durable; trazabilidad por capas | Tema 7 · RNF-03 · ADR-0014 |
| Base de datos | RDS PostgreSQL | db.t4g.micro, Single-AZ, 20 GB gp3, backups 7 días | 24/7 | F3, contratos, modelo dimensional y liquidaciones append-only | Tema 7 · RF-09 · HU 17 |
| Imágenes | Amazon ECR | arm64 | Siempre | Destino del CI; una imagen por componente | Tema 8 |
| Secretos | SSM Parameter Store (SecureString) | Nivel estándar | Siempre | Gratis; evita credenciales en el repositorio | CT-02 · ADR-0017 |
| Observabilidad | CloudWatch Logs y alarmas | Retención de 7 días | Siempre | Logs de ECS/ALB y alarmas de salud | HU 18 |
| Costos | AWS Budgets + SNS por correo | 1 presupuesto | Siempre | Aviso antes de pasarse del presupuesto | HU 23 · E-07 |
| Kubernetes | Amazon EKS | 1 componente | **Solo Sprint 5 y demo** | El plano de control solo cuesta ~73 USD/mes | Tema 19 · ADR-0018 |
| Infraestructura como código | Terraform | — | — | `apply` y `destroy` reproducibles | HU 17, 38 · ADR-0011 |
| CI/CD | GitHub Actions + OIDC | — | — | Lint, pruebas, build, push a ECR y deploy, sin llaves guardadas | Temas 17–18 · HU 31 |
| Analítica | Power BI Desktop vía túnel SSM a RDS | — | — | Sin exponer la base de datos a internet | RF-08 · HU 35 · ADR-0019 |

## 3. Flujos (números del diagrama)

| # | Flujo | Reglas que cubre |
|---|---|---|
| ①–③ | El sello llama por HTTPS con su token → ALB → API de titulares → lee su liquidación en RDS (Gold). Si pide datos de otro titular, recibe 403 | RN-11, CA-08, RF-05 |
| ④–⑥ | El simulador publica eventos F2 en RabbitMQ (cola durable, mensaje persistente) → el consumidor confirma con ACK después de escribir en S3 Bronze | RF-01, RNF-04 |
| ⑦ | Airflow lanza los jobs de Spark: diario (Silver) y mensual el día 3 (Gold) | RF-04 |
| ⑧ | Spark: Bronze → Silver (sesiones, validez, fraude) → Gold (liquidación). Consulta el % vigente en la API F4 | RN-01 a RN-08, RN-10 |
| ⑨ | Spark carga en RDS el modelo dimensional y la liquidación (append-only, con ID de liquidación por reproducción) | RNF-02, RNF-03, RF-09 |
| ⑩ | Airflow trae F6 (tasas) y F7 (países) por la NAT | RN-05 |
| ⑪ | GitHub Actions construye y sube las imágenes a ECR y despliega en ECS (OIDC, sin llaves) | CT-02 |
| ⑫ | Power BI Desktop se conecta a RDS por túnel SSM | RN-09, RF-07, RF-08 |

## 4. Qué se tomó y qué se descartó de la arquitectura de referencia

| En la imagen de referencia | En SonoraPlay | Motivo |
|---|---|---|
| Elastic Load Balancer | **Se mantiene** (ALB) | Lo exige el tema 9 |
| EC2 + Auto Scaling Group | **Se reemplaza** por ECS Fargate | No hay servidores que parchear; se paga por contenedor |
| RDS con backups | **Se mantiene** | Tema 7; backups automáticos de 7 días |
| Amazon S3 | **Se mantiene** como Data Lake | Tema 7 |
| Email Notifications | **Se mantiene** como Budgets + SNS | Alertas de costo y salud |
| DynamoDB (sesiones) | **Se descarta** | La API no guarda sesión: usa un token firmado |
| Memcache | **Se descarta** | Ningún requisito pide caché; sería costo sin regla que lo justifique |
| Amazon SES | **Se descarta** | No se envían correos a los sellos; para alertas basta SNS |

## 5. Costo estimado con todo prendido

Supuestos: región us-east-1, 730 h al mes, precios de lista de referencia y volumen de desarrollo. **Hay que confirmarlo en la HU 23 con la AWS Pricing Calculator.**

| Componente | USD/mes aprox. |
|---|---|
| Instancia NAT t4g.nano + disco | 4 |
| EC2 RabbitMQ t4g.small + 20 GB | 14 |
| EC2 Airflow t4g.medium + 30 GB | 27 |
| RDS db.t4g.micro + 20 GB | 14 |
| ALB (hora + LCU) | 18 |
| 2 APIs en Fargate ARM On-Demand | 15 |
| Simulador y consumidor en Fargate Spot | 5 |
| IPv4 públicas (2 del ALB + 1 de la NAT) | 11 |
| Jobs Spark en Spot (diarios + mensual) | 2–5 |
| S3, ECR, CloudWatch, SNS, Budgets | 4–6 |
| **Total sin EKS** | **≈ 115–120** |
| EKS, solo en el Sprint 5 y la demo (~2 semanas) | +35 plano de control + nodos |

Por encima de lo que más pesa hoy (ALB, EC2 de Airflow y RDS), solo quedaría recortar apagando servicios, y eso contradice el requisito de mantener todo prendido.

## 6. Riesgos de esta versión

| Riesgo | Mitigación |
|---|---|
| La instancia NAT es un punto único de falla | Solo afecta la salida a F6/F7; S3 va por el endpoint. Alarma de CloudWatch con recuperación automática |
| Fargate Spot interrumpe el consumidor | ACK manual + cola durable: el mensaje vuelve a la cola (se prueba en la HU 20) |
| Fargate Spot interrumpe la liquidación del día 3 | Reintentos en el DAG. Si pasa del límite, cambiar ese job a On-Demand (decisión en ADR-0012) |
| RDS Single-AZ | Aceptable para un proyecto académico; backups automáticos. Multi-AZ duplicaría el costo |
| Airflow y RabbitMQ en EC2 exigen mantenimiento | Imágenes oficiales con docker compose; se reconstruyen con Terraform |

## 7. Pendientes para la v2

- Confirmar los costos en la calculadora (HU 23).
- Las ambigüedades de las RN ya tienen supuestos en [ambiguedades-rn.md](../analisis/ambiguedades-rn.md) (HU 02); si el docente responde distinto, pueden cambiar la zona horaria y el país que define la bolsa.
- Ver el [registro de ADR](../adr/README.md): cada decisión pendiente ya tiene su historia asignada.
