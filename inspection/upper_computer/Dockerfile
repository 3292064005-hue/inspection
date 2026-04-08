FROM ros:humble-ros-base-jammy
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ROS_DISTRO=humble
RUN apt-get update && apt-get install -y --no-install-recommends curl git ca-certificates python3-pip build-essential && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY requirements-dev.txt constraints.txt ./
RUN python3 -m pip install --upgrade pip && python3 -m pip install --no-cache-dir -r requirements-dev.txt -c constraints.txt
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm ci --prefer-offline --no-audit --progress=false
COPY . .
CMD ["bash", "scripts/validate_workspace.sh"]
