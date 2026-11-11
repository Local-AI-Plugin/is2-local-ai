FROM eclipse-temurin:21-jre
ARG JENA_VERSION=6.2.0
WORKDIR /opt
ADD https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-${JENA_VERSION}.tar.gz /tmp/fuseki.tar.gz
ADD https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-${JENA_VERSION}.tar.gz.sha512 /tmp/fuseki.sha512
RUN set -eu; expected="$(awk '{print $1}' /tmp/fuseki.sha512)"; \
    test "${#expected}" -eq 128; \
    printf '%s  %s\n' "$expected" /tmp/fuseki.tar.gz | sha512sum -c -; \
    tar -xzf /tmp/fuseki.tar.gz; \
    mv "apache-jena-fuseki-${JENA_VERSION}" fuseki; \
    rm /tmp/fuseki.tar.gz /tmp/fuseki.sha512
ENV FUSEKI_HOME=/opt/fuseki
ENV FUSEKI_BASE=/work/run
WORKDIR /work
COPY config.ttl /work/config.ttl
EXPOSE 3030
ENTRYPOINT ["java", "-Xms128m", "-Xmx512m", "-jar", "/opt/fuseki/fuseki-server.jar"]
CMD ["--config=/work/config.ttl"]
