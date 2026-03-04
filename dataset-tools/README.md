# Dataset Tools (Preview de Features)

Este diretório contém um fluxo único para você gerar tráfego normal no hub por 1 minuto, capturar PCAP e extrair features de flow com NFStream.

## Arquivos

- `scripts/preview_flow_features.py`: pipeline completo (captura + tráfego + extração)
- `requirements.txt`: dependências para este fluxo
- `output/`: artefatos gerados (`.pcap` e `.csv`)

## Pré-requisitos

1. Hub e devices rodando nas portas 8000, 8001, 8002, 8003.
2. `tcpdump` instalado.
3. Permissão de captura (normalmente com `sudo`).

## Instalação

Na raiz do projeto:

```bash
cd smart-home-hub-poc
python3 -m venv .venv
source .venv/bin/activate
pip install -r dataset-tools/requirements.txt
```

## Execução (1 minuto)

```bash
sudo .venv/bin/python dataset-tools/scripts/preview_flow_features.py \
  --duration 60 \
  --workers 6
```

Exemplo capturando faixa de portas:

```bash
sudo .venv/bin/python dataset-tools/scripts/preview_flow_features.py \
  --duration 60 \
  --workers 6 \
  --ports 8000-9000 \
  --pcap-out dataset-tools/output/normal_8k_9k.pcap \
  --csv-out dataset-tools/output/normal_8k_9k.csv
```

## Saídas esperadas

- PCAP: `dataset-tools/output/traffic_preview.pcap`
- CSV (features brutas do NFStream): `dataset-tools/output/flow_features_preview.csv`

O script também imprime no terminal:
- total de requests
- requests por endpoint
- erros
- req/s
- número de flows processados
- quantidade de colunas disponíveis
- nomes das primeiras colunas
