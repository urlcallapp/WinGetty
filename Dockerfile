# Use an official Python runtime as the base image
FROM python:3.9-alpine

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

RUN apk add --no-cache build-base openssl-dev libffi-dev
# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Flask app code into the container
COPY app/ app/
COPY wingetty_import/ wingetty_import/
COPY client/ client/
COPY tests/ tests/
COPY scripts/ scripts/
COPY NOTICE.md .
COPY requirements-dev.txt .
COPY tailwind.config.js .
COPY package.json .
COPY package-lock.json .
COPY src/ src/ 
COPY settings.toml .
COPY config.py .
COPY migrations/ migrations/
COPY start.sh .

RUN ["chmod", "+x", "./start.sh"]

# Set the environment variables
ENV FLASK_APP=app
ENV FLASK_ENV=production

# Build the CSS using Tailwind
RUN apk update && apk add --no-cache nodejs npm && apk add tzdata
RUN npm ci
RUN npm run build:css

# Bake the corresponding-source archive into the image so the running
# instance can offer it at /source/archive (AGPL-3.0), also on air-gapped
# networks. chmod +x because the build context may not preserve modes.
RUN chmod +x scripts/build-source-archive.sh && sh scripts/build-source-archive.sh


# Expose port 8080 for Gunicorn
EXPOSE 8080

# Start the app using Gunicorn boot.sh
ENTRYPOINT ["./start.sh"]
