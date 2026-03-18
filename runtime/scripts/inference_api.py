import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import joblib
from ae import DeepAutoEncoder


def load_hub_model(model_path):
    """
    Carrega o modelo. Retorna parâmetros, scaler e threshold.
    model_path: nome da pasta com o modelo.
    """
    device = get_device()

    model = DeepAutoEncoder(
        d_features=7,
        dim_1=16,
        dim_2=8,
        d_latent_space=3,
        dropout=0.1
    ).to(device)

    try:
        model_state_dict = torch.load(f"{model_path}/net_anomaly_ae_demo.pth", map_location=device)
        model.load_state_dict(model_state_dict)
        scaler = joblib.load(f"{model_path}/scaler.pkl")
        scaler.feature_names_in_ = None
        threshold = joblib.load(f"{model_path}/threshold.joblib")

    except Exception as e:
        print(f"Loading failed.\n{e}")

    return model, scaler, threshold


def is_anomaly_hub(hub_model, hub_scaler, hub_threshold, csv_file):
    """
    Inferencia para detectar anomalias a nível de hub.
    hub_model/scaler/threshold: Modelo carregado com load_ae.
    csv_file: csv com uma janela de entradas de 10 segundos.
    Retorna 1 para anomalias e 0 para trafego normal. 
    """
    x = _csv_to_tensor_hub(csv_file, hub_scaler)

    with torch.no_grad():
        x_recon = hub_model(x) 
        mse = torch.mean((x - x_recon) ** 2, dim=tuple(range(1, x.dim())))
        pred = (mse > hub_threshold).int().item()

    return pred


def load_flows_model(model_path):
    """
    Carrega o modelo. Retorna parâmetros, scaler e threshold.
    model_path: nome da pasta com o modelo.
    """
    device = get_device()

    model = DeepAutoEncoder(
        d_features=24,
        dim_1=16,
        dim_2=8,
        d_latent_space=4,
        dropout=0.1
    ).to(device)

    try:
        model_state_dict = torch.load(f"{model_path}/net_anomaly_ae_demo.pth", map_location=device)
        model.load_state_dict(model_state_dict)
        scaler = joblib.load(f"{model_path}/scaler.pkl")
        scaler.feature_names_in_ = None
        threshold = joblib.load(f"{model_path}/threshold.joblib")

    except Exception as e:
        print(f"Loading failed.\n{e}")

    return model, scaler, threshold


def is_anomaly_flows(flows_model, flows_scaler, flows_threshold, csv_file):
    """
    Inferencia para detectar anomalias a nível de flows.
    flows_model/scaler/threshold: Modelo carregado com load_ae.
    csv_file: csv com uma janela de entradas de 10 segundos.
    Retorna 1 para anomalias e 0 para trafego normal. 
    """
    x = _csv_to_tensor_flows(csv_file, flows_scaler)

    with torch.no_grad():
        x_recon = flows_model(x) 
        mse = torch.mean((x - x_recon) ** 2, dim=tuple(range(1, x.dim())))
        pred = (mse > flows_threshold).int().item()

    return pred


################################################################################
#                               Auxiliary
################################################################################


def get_device():
    device = "cpu"
    if torch.accelerator.is_available():
        device = torch.accelerator.current_accelerator()
    return device


def _entropy(series):
    probs = series.value_counts(normalize=True)
    return -(probs * np.log2(probs)).sum()


def _csv_to_tensor_hub(csv_file, scaler):
    device = get_device()

    df = pd.read_csv(csv_file)

    x = _build_features_runtime_hub(df)
    x = scaler.transform(x.reshape(1, -1))
    x = torch.from_numpy(x).float().to(device)

    return x


def _build_features_runtime_hub(df):
    count = len(df)

    if count == 0:
        raise ValueError("Empty window CSV")

    requests_total = count
    error_rate = df["is_error"].mean()
    auth_failure_rate = df["is_auth_failure"].mean()
    unique_path_ratio = df["path"].nunique() / count
    avg_query_length = df["query_length"].mean()
    entropy_mean = df["query_entropy"].mean()
    entropy_max = df["query_entropy"].max()

    return np.array([
        requests_total,
        error_rate,
        auth_failure_rate,
        unique_path_ratio,
        avg_query_length,
        entropy_mean,
        entropy_max,
    ], dtype=np.float32)


def _csv_to_tensor_flows(csv_file, scaler):
    device = get_device()

    df = pd.read_csv(csv_file)

    x = _build_features_runtime_flows(df)
    x = scaler.transform(x.reshape(1, -1))
    x = torch.from_numpy(x).float().to(device)

    return x


def _build_features_runtime_flows(df):

    return np.array([
        _entropy(df["dst_port"]),
        _entropy(df["application_name"]),
        len(df),

        df["bidirectional_packets"].sum(),
        df["bidirectional_packets"].mean(),
        df["bidirectional_bytes"].sum(),
        df["bidirectional_bytes"].mean(),
        df["bidirectional_duration_ms"].sum(),
        df["bidirectional_duration_ms"].mean(),

        df["src2dst_packets"].sum(),
        df["src2dst_packets"].mean(),
        df["src2dst_bytes"].sum(),
        df["src2dst_bytes"].mean(),
        df["src2dst_duration_ms"].sum(),
        df["src2dst_duration_ms"].mean(),

        df["dst2src_packets"].sum(),
        df["dst2src_packets"].mean(),
        df["dst2src_bytes"].sum(),
        df["dst2src_bytes"].mean(),
        df["dst2src_duration_ms"].sum(),
        df["dst2src_duration_ms"].mean(),

        df["bidirectional_packets"].max(),
        df["src2dst_packets"].max(),
        df["dst2src_packets"].max(),
    ], dtype=np.float32)


if __name__ == "__main__":
    print("Import this module from the runtime scripts or call the specific inference entrypoints.")
