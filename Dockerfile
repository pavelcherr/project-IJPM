FROM python:3.11.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=cryptography -r requirements.txt

COPY harness ./harness
COPY feasibility ./feasibility
COPY math_classifier ./math_classifier
COPY run_agent.py .

# Organizers override the entrypoint:
# python /app/run_agent.py --tasks-dir /data/tasks
