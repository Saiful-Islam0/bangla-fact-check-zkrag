FROM node:20-bookworm-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm ci

COPY . .

RUN npm run compile
RUN chmod +x ./entrypoint.sh

EXPOSE 8545 8787

CMD ["./entrypoint.sh"]
