FROM golang:1.27.3-alpine3.24@sha256:fa3d596898d9f126af7c01d14ee7597bab3f39cccf392ef36b69fe77cd681f18 AS build
RUN apk add --no-cache python3 git
WORKDIR /source
COPY --from=manager-source openbao-v2.7.2.tar.gz /tmp/source.tar.gz
RUN echo '11b48e34ea1bbad5db4044ced904c7f1a4265da5230551463846c6745e507797  /tmp/source.tar.gz' | sha256sum -c - && tar -xzf /tmp/source.tar.gz --strip-components=1 && rm /tmp/source.tar.gz
ENV GOMAXPROCS=1 GOMEMLIMIT=512MiB GOGC=20 CGO_ENABLED=0 GOTOOLCHAIN=local
COPY patch_jose3.py regression_test.go /patch/
RUN --mount=type=cache,target=/go/pkg/mod go mod download github.com/go-jose/go-jose/v3 && mkdir -p /patched && cp -R /go/pkg/mod/github.com/go-jose/go-jose/v3@v3.0.5 /patched/jose3 && chmod -R u+w /patched/jose3 && python3 /patch/patch_jose3.py /patched/jose3 && cp /patch/regression_test.go /patched/jose3/f17_regression_test.go
RUN --mount=type=cache,target=/go/pkg/mod go mod edit -replace=github.com/go-jose/go-jose/v3=/patched/jose3 && go get github.com/go-jose/go-jose/v4@v4.1.6
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build cd /patched/jose3 && go test -p 1 ./... > /patched/jose3-tests.txt
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build go build -p 1 -trimpath -ldflags='-X github.com/openbao/openbao/v2/internal/version.fullVersion=2.7.2 -X github.com/openbao/openbao/v2/internal/version.VersionMetadata=opspilot-f17.1' -o /out/bao . && go version -m /out/bao > /out/build-modules.txt && cp /patched/jose3/f17-patch-proof.json /patched/jose3-tests.txt /patch/patch_jose3.py /out/ && cp go.mod go.sum /out/

FROM quay.io/openbao/openbao:2.7.2@sha256:5046911075e137e154ce49ab051502f4ec7cf367d484ae4a4dce665d9b90561f
USER root
RUN apk --no-cache upgrade
COPY --from=build /out/bao /usr/bin/bao
COPY --from=build /out/build-modules.txt /out/f17-patch-proof.json /out/jose3-tests.txt /out/patch_jose3.py /out/go.mod /out/go.sum /usr/share/opspilot-manager/
USER openbao
