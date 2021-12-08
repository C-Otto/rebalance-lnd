FROM python:3.10-alpine3.14 

RUN apk add --update --no-cache linux-headers gcc g++ git openssh-client \
    && apk add libstdc++ --no-cache --repository http://dl-3.alpinelinux.org/alpine/edge/testing/ --allow-untrusted \
    && git clone --depth=1 https://github.com/C-Otto/rebalance-lnd.git \
    && rm -rf rebalance-lnd/.github \
    && cd rebalance-lnd \
    && /usr/local/bin/python -m pip install --upgrade pip \
    && pip install -r requirements.txt \
    && cd / \
    && apk del linux-headers gcc g++ git openssh-client \
    && mkdir /root/.lnd

VOLUME [ "/root/.lnd" ]

WORKDIR /

ENTRYPOINT [ "/rebalance-lnd/rebalance.py" ]
