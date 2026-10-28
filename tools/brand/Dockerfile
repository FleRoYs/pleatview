# Renders PleatView's brand assets: SVG to PNG (librsvg), the wordmark as outlines
# (Poppins, shaped with HarfBuzz), and composites (Pillow).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends librsvg2-bin curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir -q pillow fonttools uharfbuzz \
 && mkdir -p /fonts \
 && for w in Medium SemiBold; do \
      curl -fsSL -o /fonts/Poppins-$w.ttf https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-$w.ttf; \
    done
WORKDIR /src
