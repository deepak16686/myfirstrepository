# Base: localhost:5001/apm-repo/demo/amazoncorretto:17-alpine-jdk
FROM localhost:5001/apm-repo/demo/amazoncorretto:17-alpine-jdk

WORKDIR /app

COPY target/app.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]
