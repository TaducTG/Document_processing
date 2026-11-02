# Enterprise Document Processing & Workflow Automation Platform

[![CI Pipeline](https://github.com/ductm85/enterprise-doc-processor/actions/workflows/ci.yml/badge.svg)](https://github.com/ductm85/enterprise-doc-processor/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)

A scalable, event-driven enterprise document processing and workflow automation platform built with **Python (FastAPI)**, **Clean Architecture**, and a **Zero AWS Cost** distributed infrastructure stack.

The platform ingests high-volume multi-format documents (PDF, DOCX, XLSX, Scanned Images), executes asynchronous ETL pipelines with automated retry and dead-letter queue (DLQ) mechanics, streams real-time status updates via Server-Sent Events (SSE), and renders live telemetry on an interactive React dashboard.

---

## 🏛 System Architecture

```
[ React + Tailwind Dashboard ]
              │
              ▼ (Multipart / Presigned Upload / SSE Stream)
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Gateway (Async / ASGI)                             │
│  - Presentation Layer: Document Ingestion, Auth, SSE Stream │
│  - Application Layer: Document Use Cases & Task Dispatcher  │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
        (Save Raw File)                (Enqueue Task)
               ▼                               ▼
┌────────────────────────────┐    ┌───────────────────────────┐
│ MinIO Object Storage (S3)  │    │ Redis 7                   │
│ - Bucket: raw-documents    │    │ - Task Broker (Queue)     │
│ - Bucket: processed-output │    │ - Pub/Sub Channel (Events)│
└──────────────▲─────────────┘    └────────────┬──────────────┘
               │                               │
               │ (Download & Process)          ▼ (Consume Task)
┌──────────────┴──────────────────────────────────────────────┐
│  Distributed ETL Workers (Celery)                           │
│  - Multi-format Extractor (PyMuPDF, pdfplumber, python-docx)│
│  - Fallback OCR Engine (PaddleOCR / Tesseract)              │
│  - Fault Tolerance: Exponential Backoff & Dead Letter Queue │
└──────────────────────────────┬──────────────────────────────┘
                               │
                      (Save Structured Result)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  PostgreSQL 16                                              │
│  - Relational Schema (Documents, Processing Jobs, Tasks)    │
│  - JSONB Metadata (Extracted Content with GIN Indexing)     │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚡ Key Highlights & Zero-Cost Cloud Mapping

| AWS Service (Enterprise CV) | Open-Source 0-Cost Alternative | Architectural Role |
| :--- | :--- | :--- |
| **Amazon S3** | **MinIO** | S3 API-compatible local object storage (uses `boto3`) |
| **AWS Lambda** | **Celery + Redis Worker** | Asynchronous ETL compute without 15-min timeout limits |
| **Amazon DynamoDB** | **PostgreSQL JSONB** | Flexible schema & fast metadata lookup with GIN index |
| **Amazon RDS** | **PostgreSQL 16 (Docker)** | Relational persistence with SQLAlchemy async session |
| **Redis ElastiCache** | **Redis 7 (Docker)** | Task queue broker + Real-time Pub/Sub progress broadcaster |
| **Amazon CloudWatch** | **Prometheus + Grafana** | Standard metrics collection & observability dashboard |

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Docker & Docker Compose
- Python 3.11+

### 2. Launch Infrastructure Services
```bash
docker compose up -d
```
MinIO Console: [http://localhost:9001](http://localhost:9001) (User: `minioadmin` / Pass: `minioadminpassword`)

### 3. Run Automated Tests
```bash
pytest tests/ -v
```

