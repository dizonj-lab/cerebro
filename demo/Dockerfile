# Build the static demo, then serve it with nginx.
#   docker build -t cerebro-demo . && docker run --rm -p 4300:80 cerebro-demo   ->  http://localhost:4300
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
