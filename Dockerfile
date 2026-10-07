# Stage 1: Build the React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY bangla-fact-check-main/package*.json ./
RUN npm ci
COPY bangla-fact-check-main/ ./
RUN npm run build

# Install the pinned Node runtime dependencies used by Poseidon/snarkjs.
FROM node:20-bookworm-slim AS zk-builder
WORKDIR /zk
COPY zk/package*.json ./
RUN npm ci --omit=dev --ignore-scripts

# Stage 2: Build the Python backend and copy frontend build
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY --from=zk-builder /usr/local/bin/node /usr/local/bin/node

# Install system dependencies for OCR and images
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    tesseract-ocr-ben \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU and Python dependencies
COPY code/requirements.txt .
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.2.2 torchvision==0.17.2 \
    && grep -vE '^(torch|torchvision)($|[>=~=!])' requirements.txt > requirements.docker.txt \
    && pip install -r requirements.docker.txt

# Copy backend files
COPY code/ .

# Copy ZK scripts, circuit source, generated proving artifacts, and runtime deps.
COPY zk/ ./zk/
COPY --from=zk-builder /zk/node_modules ./zk/node_modules
ENV ZKRAG_ZK_ROOT=/app/zk \
    ZKRAG_PROOF_DIR=/app/zk_proofs \
    ZKRAG_AUDIT_DIR=/app/zk_audits

# Copy built frontend assets to /app/dist
COPY --from=frontend-builder /app/dist ./dist

# Create folders for volumes
RUN mkdir -p claim_metadata claim_snapshots flagged_sources uploaded_images image_metadata zk_proofs zk_audits

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
