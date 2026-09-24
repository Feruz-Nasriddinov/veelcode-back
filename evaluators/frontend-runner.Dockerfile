FROM node:24-slim

WORKDIR /work

RUN npm init -y > /dev/null \
    && npm install --no-audit --no-fund \
        react@19.3.0 \
        react-dom@19.3.0 \
        vite@8.3.0 \
        @vitejs/plugin-react@6.1.1 \
        next@16.3.6 \
        typescript@5.9.3 \
        @types/react@19.3.0 \
        @types/react-dom@19.3.0 \
        @types/node@26.6.2 \
    && npm cache clean --force \
    && chmod -R a+rwX /work

COPY serve.js /opt/veelcode/serve.js
ENV NEXT_TELEMETRY_DISABLED=1
