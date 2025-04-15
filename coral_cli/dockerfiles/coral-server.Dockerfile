# Use an official OpenJDK runtime as a parent image
FROM eclipse-temurin:17-jre-jammy

# Set the working directory
WORKDIR /app

# --- IMPORTANT ---
# This Dockerfile is intended to be built with the 'coral_cli' directory as the build context.
# It expects the server JAR at 'binaries/coral-server.jar' within that context.
ARG JAR_FILE=binaries/coral-server.jar

# Copy the executable JAR file from the build context into the container
COPY ${JAR_FILE} coral-server.jar

# Make port 3001 available
EXPOSE 3001

# Run the JAR file with SSE mode on port 3001 when the container launches
CMD ["java", "-jar", "coral-server.jar", "--sse-server-ktor", "3001"] 