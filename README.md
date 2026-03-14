# smart-home-hub-poc

PoC leve para demo de detecção de anomalias de rede em ambiente de Smart Home, pensado para rodar em Linux e Raspberry Pi.

Componentes:
- `hub/`: orquestrador FastAPI (autenticação, proxy para devices, eventos, upload firmware, logs JSON).
- `devices/light/`: serviço de luzes simuladas, controlando múltiplas instâncias lógicas.
- `devices/lock/`: serviço de fechaduras simuladas, controlando múltiplas instâncias lógicas.
- `devices/thermostat/`: serviço de termostatos simulados, controlando múltiplas instâncias lógicas.
- `common/`: utilitários compartilhados (config, modelos, logging, rate limit).

## Estrutura

```text
smart-home-hub-poc/
├── common/
├── hub/
├── devices/
│   ├── light/
│   ├── lock/
│   └── thermostat/
├── docker/
├── data/
├── tests/
├── requirements.txt
└── README.md
```

## Portas padrão

- Hub: `8000`
- Light: `8001`
- Lock: `8002`
- Thermostat: `8003`

## Inventário lógico padrão

O hub já sobe com um inventário estático de devices lógicos:

- Lights: `light_1` a `light_10`
- Locks: `lock_1` a `lock_6`
- Thermostats: `thermostat_1` a `thermostat_4`

Cada serviço (`light`, `lock`, `thermostat`) atende várias instâncias via `device_id`.

## Variáveis de ambiente (hub)

- `HUB_API_KEY` (default: `devkey`)
- `HUB_VERSION` (default: `0.1.0`)
- `HUB_LOG_TO_FILE` (default: `0`)  
  Quando `1`, também grava em `./data/logs/hub.jsonl`
- `HUB_RATE_LIMIT_ENABLED` (default: `0`)
- `HUB_RATE_LIMIT_RPM` (default: `60`)
- `HUB_LIGHT_URL` (default: `http://localhost:8001`)
- `HUB_LOCK_URL` (default: `http://localhost:8002`)
- `HUB_THERMOSTAT_URL` (default: `http://localhost:8003`)

## Variáveis de ambiente (devices)

- `HUB_URL` (default: `http://localhost:8000`) para `POST /emit_event`

## Rodando nativo (Linux/Raspberry)

No diretório do projeto:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Suba cada serviço em um terminal:

```bash
# terminal 1
uvicorn hub.main:app --host 0.0.0.0 --port 8000
```

```bash
# terminal 2
uvicorn devices.light.main:app --host 0.0.0.0 --port 8001
```

```bash
# terminal 3
uvicorn devices.lock.main:app --host 0.0.0.0 --port 8002
```

```bash
# terminal 4
uvicorn devices.thermostat.main:app --host 0.0.0.0 --port 8003
```

## Rodando com Docker Compose

Da raiz do projeto:

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Exemplos com curl

Defina uma variável para a API key:

```bash
export HUB_API_KEY=devkey
```

### 1) Health do hub

```bash
curl -s http://localhost:8000/health
```

### 2) Enviar comando para light

```bash
curl -s -X POST http://localhost:8000/command \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${HUB_API_KEY}" \
  -d '{"device_id":"light_1","action":"turn_on","request_id":"req-001"}'
```

### 3) Consultar state de lock

```bash
curl -s "http://localhost:8000/state?device_id=lock_1" \
  -H "X-API-Key: ${HUB_API_KEY}"
```

### 4) Enviar evento manual para o hub

```bash
curl -s -X POST http://localhost:8000/event \
  -H "Content-Type: application/json" \
  -d '{"device_id":"light_1","event":"heartbeat","value":{"ok":true}}'
```

### 5) Listar eventos recentes

```bash
curl -s "http://localhost:8000/events?limit=20"
```

### 6) Upload de firmware

```bash
echo "firmware-demo" > sample_fw.bin
curl -s -X POST http://localhost:8000/firmware \
  -H "X-API-Key: ${HUB_API_KEY}" \
  -F "file=@sample_fw.bin"
```

### 7) Busca operacional no painel legado (demo)

Endpoint de demonstração montado no hub: `GET /demo/search?q=<termo>`

Uso normal na narrativa:
- Busca rápida por `device_id` ou texto de eventos recentes
- Apoio a troubleshooting interno

Exemplo:

```bash
curl -s "http://localhost:8000/demo/search?q=lock_1"
```

Observação: este endpoint foi mantido com template inseguro de propósito para demonstrar comportamento anômalo.

### 8) Endpoint de PoC para CVE-2023-25577 (Werkzeug multipart)

Endpoint de demonstração montado no hub: `POST /demo/upload-preview`

Uso normal na narrativa:
- Endpoint de suporte para upload de formulário diagnóstico
- Mede métricas básicas de parsing de multipart (`parse_ms`, total de campos/arquivos)

Exemplo simples:

```bash
curl -s -X POST http://localhost:8000/demo/upload-preview \
  -F "field_1=ok" \
  -F "field_2=ok"
```

PoC controlada (baseline vs payload com muitos campos multipart):

```bash
.venv/bin/python dataset-tools/scripts/poc_cve_2023_25577.py \
  --url http://localhost:8000/demo/upload-preview \
  --runs 3 \
  --baseline-fields 20 \
  --attack-fields 12000
```

Saída esperada da PoC:
- latência média do cliente e `parse_ms` do servidor no baseline
- latência média e `parse_ms` no cenário de ataque
- fator de amplificação (`x`) entre ataque e baseline

## Emitir evento a partir de um device

Exemplo com light:

```bash
curl -s -X POST http://localhost:8001/emit_event \
  -H "Content-Type: application/json" \
  -d '{"device_id":"light_2","event":"motion_detected","value":{"zone":"kitchen"}}'
```

## Expor com ngrok (resumo)

Depois de subir o hub localmente:

```bash
ngrok http 8000
```

Use a URL pública do ngrok para chamar endpoints do hub. Endpoints protegidos continuam exigindo `X-API-Key`.
