FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv pip install --system .
COPY . .
EXPOSE 8000 8765
ENV WS_HOST="0.0.0.0" \
    WS_PORT="8765" \
    HTTP_HOST="0.0.0.0" \
    HTTP_PORT="8000"
CMD ["python", "-m", "knockout_whist.bin.server", "--ws-host", "${WS_HOST}", "--ws-port", "${WS_PORT}", "--http-host", "${HTTP_HOST}", "--http-port", "${HTTP_PORT}"]
