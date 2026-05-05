FROM node:20.19.2-alpine AS builder

ARG CHROMADB_ADMIN_REF=bfee61bb2c6f256d24e5e05e349657196e3a96cd

WORKDIR /app
RUN apk add --no-cache git \
  && git clone https://github.com/flanker/chromadb-ui.git . \
  && git checkout "$CHROMADB_ADMIN_REF"
COPY patch-delete-support.js /tmp/patch-delete-support.js
RUN node /tmp/patch-delete-support.js \
  && rm /tmp/patch-delete-support.js
RUN npm install --no-audit --no-fund
RUN npm run build

FROM node:20.19.2-alpine AS production

ENV NODE_ENV=production
ENV CHROMADB_ADMIN_DEFAULT_CONNECTION=http://chromadb:8000
ENV CHROMADB_ADMIN_DEFAULT_TENANT=default_tenant
ENV CHROMADB_ADMIN_DEFAULT_DATABASE=default_database

WORKDIR /app
COPY --from=builder /app/package.json /app/package-lock.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/src ./src
COPY --from=builder /app/next.config.js ./next.config.js

COPY patch-defaults.js /tmp/patch-defaults.js
RUN node /tmp/patch-defaults.js \
  && node --check /app/.next/server/app/page.js \
  && node --check /app/.next/server/app/api/collections/route.js \
  && node --check /app/.next/server/app/api/collections/[collectionName]/records/route.js \
  && rm /tmp/patch-defaults.js \
  && chown -R node:node /app

USER node
EXPOSE 3001
CMD ["npm", "start"]
