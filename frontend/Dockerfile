# Plugins (see src/plugins/README.md): this stage is all an image gets in src/plugins/. A build can replace it
# with a folder of plugin folders by passing a build context named "plugins".
FROM scratch AS plugins
COPY src/plugins/README.md /

FROM node:24-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
COPY --from=plugins / src/plugins/
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
