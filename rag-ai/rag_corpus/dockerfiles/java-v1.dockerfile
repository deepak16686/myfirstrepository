ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/amazoncorretto:17-alpine-jdk

WORKDIR /app

COPY target/app.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]
