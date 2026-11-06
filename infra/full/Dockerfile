FROM golang:1.27.3-alpine3.24@sha256:fa3d596898d9f126af7c01d14ee7597bab3f39cccf392ef36b69fe77cd681f18 AS gosu-build
ADD --checksum=sha256:cd9719b775dbfedae53923c9b0dc792b66d42c51e0b36652ed6f747fbadc0164 https://codeload.github.com/tianon/gosu/tar.gz/refs/tags/1.19 /tmp/gosu.tar.gz
WORKDIR /source
RUN tar -xzf /tmp/gosu.tar.gz --strip-components=1
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/gosu .

FROM postgres@sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139 AS postgres
RUN apk --no-cache upgrade
COPY --from=gosu-build /out/gosu /usr/local/bin/gosu
RUN postgres --version | grep 'PostgreSQL) 16\.' && gosu --version && gosu postgres id

FROM otel/opentelemetry-collector:0.120.0@sha256:1daa4312b48312dbae2d543e67b77e897dd5d9c48e7651d1416cdb417026ad06 AS collector

FROM jaegertracing/all-in-one:1.66.0@sha256:9864182b4e01350fcc64631bdba5f4085f87daae9d477a04c25d9cb362e787a9 AS jaeger

FROM redis:8-alpine@sha256:21090af93f8324db2f0f0f4f38a7c60369d47d917e000c3423d89d2ae2883537 AS redis
