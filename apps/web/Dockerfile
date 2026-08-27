# syntax=docker/dockerfile:1

FROM node:22-slim AS base
WORKDIR /build

FROM base AS deps
COPY package.json package-lock.json* ./
RUN npm install

FROM base AS builder
COPY --from=deps /build/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* values are inlined into the client bundle AT BUILD TIME
# (runtime env cannot change them). The default preserves today's local
# behavior exactly (lib/api.ts falls back to http://localhost:8000).
# Production builds pass --build-arg NEXT_PUBLIC_API_URL="" — an empty
# origin makes every API call a same-origin relative fetch
# ("/api/v1/..."), which the production ALB path-routes to the API
# service, so one image works for any domain with no CORS and no
# per-domain rebuild (docs/infrastructure.md, "Single-origin routing").
ARG NEXT_PUBLIC_API_URL="http://localhost:8000"
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build

FROM base AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000
# node:22-slim already ships a non-root "node" user (uid/gid 1000).
WORKDIR /app
COPY --from=builder /build/public ./public
COPY --from=builder --chown=node:node /build/.next/standalone ./
COPY --from=builder --chown=node:node /build/.next/static ./.next/static
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
    CMD node -e "fetch('http://localhost:3000/dashboard').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
