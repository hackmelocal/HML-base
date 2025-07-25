# Use Alpine as the base image
FROM python:3.12-alpine

# Set the working directory
WORKDIR /app

# Copy the application files (commented for development)
# COPY ./app /app

# Install dependencies
RUN pip install --no-cache-dir flask Flask-Limiter requests

# Expose ports
EXPOSE 8000
EXPOSE 8080

# Command to run the application
CMD ["python", "app.py"]
