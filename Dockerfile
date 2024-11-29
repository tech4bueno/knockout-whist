FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e .
ENV PYTHONPATH="/app/src:${PYTHONPATH}" \
    PYTHONUNBUFFERED=1
EXPOSE 8000
ENV HOST="0.0.0.0" \
    PORT=8000
CMD python -m knockout_whist.bin.server --host ${HOST} --port ${PORT}
