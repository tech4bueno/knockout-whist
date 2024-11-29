FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e .
ENV PYTHONPATH="/app/src:${PYTHONPATH}" \
    PYTHONUNBUFFERED=1
EXPOSE 8000 8765
ENV WS_HOST="localhost" \
    WS_PORT=8765 \
    HTTP_HOST="0.0.0.0" \
    HTTP_PORT=8000

CMD python -m knockout_whist.bin.server \
    --ws-host ${WS_HOST} \
    --ws-port ${WS_PORT} \
    --http-host ${HTTP_HOST} \
    --http-port ${HTTP_PORT}
