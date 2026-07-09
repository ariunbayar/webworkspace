# The original PHP workspace app, served by PHP's built-in server with a
# co-located redis (phpredis + db 2) so DataStoreRedis is used — avoids the
# DataStoreFile PHP-8 warnings. PHP 7.4 matches the code's era (warning-free).
FROM php:7.4-cli

# redis-server + redis-cli for the datastore; phpredis via pecl (needs PHPIZE_DEPS)
RUN apt-get update \
    && apt-get install -y --no-install-recommends redis-server $PHPIZE_DEPS \
    && pecl install redis \
    && docker-php-ext-enable redis \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN chmod +x docker/php-entrypoint.sh

ENV DEMO_DIR=/app/static/js
EXPOSE 8081

ENTRYPOINT ["/app/docker/php-entrypoint.sh"]
