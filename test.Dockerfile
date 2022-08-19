FROM python:3.10

ENV PIP_NO_CACHE_DIR=off \
	PIP_DISABLE_PIP_VERSION_CHECK=on

COPY requirements.txt ./

# System deps:
RUN apt-get update && apt-get upgrade -y \
	# Clean cache:
	&& apt-get clean -y && rm -rf /var/lib/apt/lists/* \
	# Install python packages
	&& pip install -r requirements.txt
