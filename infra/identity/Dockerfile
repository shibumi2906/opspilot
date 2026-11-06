FROM quay.io/keycloak/keycloak:26.8.1@sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b AS keycloak
# Use the supported Java21 LTS with the vendor security fix; keep dpkg metadata.
FROM debian:trixie-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4 AS prepared
USER 0
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openjdk-21-jre-headless=21.0.13+9-1~deb13u2 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=keycloak --chown=1000:0 /opt/keycloak /opt/keycloak
# Preserve the bootstrap classpath filename; embedded Maven metadata is 33.7.2-jre.
ADD --checksum=sha256:b530942257fb935f8b2cfaa5f8eb5bd59c555fd8e8d01b8ce98912e077ea606c --chown=1000:0 https://repo.maven.apache.org/maven2/com/google/guava/guava/33.7.2-jre/guava-33.7.2-jre.jar /opt/keycloak/lib/lib/main/com.google.guava.guava-33.6.0-jre.jar
COPY --chown=1000:0 infra/identity/opspilot-realm.json /opt/keycloak/data/import/opspilot-realm.json
COPY --chown=1000:0 infra/identity/password-blacklists/common-passwords.txt /opt/keycloak/data/password-blacklists/common-passwords.txt
ENV JAVA_OPTS_KC_HEAP="-Xms64m -Xmx512m"
ENV KC_HTTP_HOST=0.0.0.0 KC_HEALTH_ENABLED=true KC_HTTP_MANAGEMENT_SCHEME=http HOME=/opt/keycloak/data
WORKDIR /opt/keycloak
USER 1000:0
RUN /opt/keycloak/bin/kc.sh build --health-enabled=true
COPY infra/identity/OpsIdentityProbe.java /tmp/OpsIdentityProbe.java
RUN mkdir /tmp/opspilot-probes && java -m jdk.compiler/com.sun.tools.javac.Main -source 21 -target 21 -d /tmp/opspilot-probes /tmp/OpsIdentityProbe.java

# F17 removes unfixed Debian expat/zlib findings with a supported Java21 runtime.
# Preserve package metadata and verify the actual JRE, Guava and truststore below.
FROM alpine:3.24@sha256:3f4d6b32e26703c6082839234f43769d5046b3ac7c910033911d1e71d8cd630a
RUN apk --no-cache upgrade && apk add --no-cache openjdk21-jre-headless ca-certificates
COPY --from=prepared --chown=1000:0 /opt/keycloak /opt/keycloak
COPY --from=prepared --chown=1000:0 /tmp/opspilot-probes /opt/opspilot-probes
ENV JAVA_OPTS_KC_HEAP="-Xms64m -Xmx512m"
ENV KC_HTTP_HOST=0.0.0.0 KC_HEALTH_ENABLED=true KC_HTTP_MANAGEMENT_SCHEME=http HOME=/opt/keycloak/data
WORKDIR /opt/keycloak
USER 1000:0
RUN /usr/bin/java -Xmx64m -cp /opt/opspilot-probes OpsIdentityProbe
ENTRYPOINT ["/bin/sh", "/opt/keycloak/bin/kc.sh"]
HEALTHCHECK --interval=10s --timeout=3s --start-period=180s --retries=30 CMD ["/usr/bin/java", "-Xmx32m", "-cp", "/opt/opspilot-probes", "OpsIdentityProbe", "health"]
