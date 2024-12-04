# Knockout Whist

A full-stack implementation of Knockout Whist.

## Architecture

```mermaid
graph LR
    subgraph Frontend["Frontend (Browser)"]
        HTML["Static HTML"]
        JS["Vanilla JavaScript"]
        CSS["Tailwind CSS"]
        HTML --- JS
        JS --- CSS
    end

    subgraph Backend["Backend"]
        Python["Game Server"]
    end

    Frontend <-->|JSON over WebSocket Connection| Backend

    style Frontend fill:#f9f9f9,stroke:#333,stroke-width:2px
    style Backend fill:#f9f9f9,stroke:#333,stroke-width:2px
    style HTML fill:#e34c26,color:#fff
    style JS fill:#f7df1e,color:#000
    style CSS fill:#06b6d4,color:#fff
    style Python fill:#306998,color:#fff
```


## Design goals

* Mobile-friendly
* Simple UI
* Seamless reconnects

## Implementation goals

* <1,000 lines of code
* Single server for simple deployment
* No frontend frameworks

## Try

Go to https://knockout-whist.onrender.com (be patient: first load takes 1min+ on Render's free plan)

## Run

### With [uv](https://docs.astral.sh/uv/)

`uvx --from knockout-whist knockout-whist`

### With pip

`pip install knockout-whist` and then `knockout-whist`

### With Docker

`docker build -t knockout-whist .` then `docker run -p 8000:8000 knockout-whist`

## Develop

```
git clone https://github.com/tech4bueno/knockout-whist
pip install -e .[test]
pytest
```

## Deploy

Deploys easily to Render's free plan.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)
