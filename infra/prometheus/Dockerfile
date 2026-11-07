# Local F19 fixture only. Real upstream server/API, patched x/net; no promtool or bundled UI.
# Upstream-supported remove_all_sd keeps only static discovery needed by this lab.
FROM golang:1.27.3-alpine3.24@sha256:fa3d596898d9f126af7c01d14ee7597bab3f39cccf392ef36b69fe77cd681f18 AS build
ADD --checksum=sha256:2709a3bd43f9d15e0cecfc33ab473d011e2a69ab29265b91398cc1b8561403c0 https://codeload.github.com/prometheus/prometheus/tar.gz/refs/tags/v3.16.0 /tmp/source.tar.gz
WORKDIR /source
RUN tar -xzf /tmp/source.tar.gz --strip-components=1
ENV GOTOOLCHAIN=local GOMAXPROCS=2 GOMEMLIMIT=512MiB CGO_ENABLED=0 GOFLAGS=-p=1
RUN --mount=type=cache,target=/go/pkg/mod go get golang.org/x/net@v0.62.0
ARG BUILD_DATE=local-f19
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -tags netgo,remove_all_sd -trimpath \
    -ldflags="-s -w -X github.com/prometheus/common/version.Version=3.16.0 -X github.com/prometheus/common/version.Revision=e2e28adeee2c5883d000fc82aca6008cfbf7e96d -X github.com/prometheus/common/version.Branch=f19-xnet-0.62.0 -X github.com/prometheus/common/version.BuildUser=local-f19 -X github.com/prometheus/common/version.BuildDate=${BUILD_DATE}" \
    -o /out/prometheus ./cmd/prometheus
RUN go version -m /out/prometheus > /out/modules.txt

FROM scratch
COPY --from=build /out/prometheus /bin/prometheus
COPY --from=build /out/modules.txt /build/modules.txt
COPY --from=build /source/LICENSE /source/NOTICE /licenses/
USER 10001:10001
EXPOSE 8443
ENTRYPOINT ["/bin/prometheus"]
