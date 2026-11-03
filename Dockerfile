# Three build stages share the same Python layers:
#   base  the application and its pinned dependencies (no user set yet)
#   lab   base + network tools (iproute2, iptables, tcpdump). ONLY for docker-compose.mitm.yml, where the
#         attacker must route and redirect traffic. The normal images never contain these tools.
#   app   the default, minimal image: runs as an unprivileged user
FROM python:3.12-slim AS base

ARG WITH_CNN=1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt requirements-cnn.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$WITH_CNN" = "1" ]; then pip install --no-cache-dir -r requirements-cnn.txt --index-url https://download.pytorch.org/whl/cpu; fi

COPY pixelproof ./pixelproof
COPY simulation ./simulation
COPY scripts ./scripts

# The mount points of the compose named volumes must exist in the image and belong to the unprivileged user:
# Docker initialises a new named volume from the image path, so without this the volume is root-owned and the
# satellite cannot write its keys or publish the public registry.
RUN useradd --create-home app \
 && mkdir -p /app/runtime /shared /home/app/keys \
 && chown app /app/runtime /shared /home/app/keys \
 && chmod 700 /home/app/keys


FROM base AS lab
RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 iptables tcpdump \
 && rm -rf /var/lib/apt/lists/*


FROM base AS app
USER app
EXPOSE 8000 8081
CMD ["uvicorn", "pixelproof.api:app", "--host", "0.0.0.0", "--port", "8000"]
