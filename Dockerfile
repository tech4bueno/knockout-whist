FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install -e .
EXPOSE 8000
ENV HOST="0.0.0.0" \
    PORT=8000
CMD python -m knockout_whist.bin.server --host ${HOST} --port ${PORT}
