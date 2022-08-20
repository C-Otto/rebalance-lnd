FROM python:3.10-alpine3.14 

ENV PIP_NO_CACHE_DIR=off \
	PIP_DISABLE_PIP_VERSION_CHECK=on

COPY requirements.txt ./

# System deps:
RUN apk add --update --no-cache  \
	linux-headers \
	gcc \
	g++ \
	git openssh-client \
	&& apk add libstdc++ --no-cache --repository http://dl-3.alpinelinux.org/alpine/edge/testing/ --allow-untrusted \
	# Install python packages
	&& pip install -r requirements.txt \
	# Remove system deps
	&& apk del linux-headers gcc g++ git openssh-client
