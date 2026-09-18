# CEREBRO Web
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* values are inlined into the browser bundle at BUILD time; they
# cannot be changed by a runtime environment variable.
#
# Empty is correct everywhere: the browser calls /api on the origin that served
# the page, and src/app/api/[...path]/route.ts proxies it to the backend using
# INTERNAL_API_BASE_URL, which IS read at runtime.
ARG NEXT_PUBLIC_API_BASE_URL=""
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
# Fail the image build if deployment config was frozen into the bundle.
RUN npm run check:runtime-config

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1

RUN addgroup -g 10001 -S cerebro && adduser -S -u 10001 -G cerebro cerebro

COPY --from=builder /app/public ./public
COPY --from=builder --chown=cerebro:cerebro /app/.next/standalone ./
COPY --from=builder --chown=cerebro:cerebro /app/.next/static ./.next/static

USER cerebro
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
