# Tidekeeper container image.
#
# Config, tokens, and logs live in /config; downloads land in /downloads.
# Both are declared as volumes so credentials survive container replacement.
#
#   docker build -t tidekeeper .
#   docker run --rm -it -v ./config:/config -v ./downloads:/downloads tidekeeper
#   docker run --rm -v ./config:/config -v ./downloads:/downloads tidekeeper -l "https://tidal.com/browse/track/70973230"

FROM python:3.13-slim

# ffmpeg is required to merge video streams and to convert audio containers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY TIDALDL-PY/ ./TIDALDL-PY/
COPY README.md LICENSE NOTICE ./

RUN python -m pip install --no-cache-dir ./TIDALDL-PY \
    && rm -rf /src

RUN useradd --create-home --uid 1000 tidekeeper \
    && mkdir -p /config /downloads \
    && chown -R tidekeeper:tidekeeper /config /downloads
USER tidekeeper

ENV TIDEKEEPER_DOWNLOAD_PATH=/downloads \
    PYTHONUNBUFFERED=1
VOLUME ["/config", "/downloads"]
WORKDIR /downloads

# -c keeps config, tokens, and logs on the mounted volume instead of $HOME.
ENTRYPOINT ["tidekeeper", "-c", "/config"]
