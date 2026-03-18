import torch
import torch.nn as nn
import torch.nn.utils as utils


class DeepAutoEncoder(nn.Module):
    def __init__(self, d_features, dim_1, dim_2, d_latent_space, dropout):
        super().__init__()

        self.encoder = nn.Sequential(
            nn.Linear(d_features, dim_1),
            nn.ReLU(),
            nn.Dropout(dropout),

            nn.Linear(dim_1, dim_2),
            nn.ReLU(),
            nn.Dropout(dropout),

            nn.Linear(dim_2, d_latent_space),
            nn.ReLU(),
        )

        self.decoder = nn.Sequential(
            nn.Linear(d_latent_space, dim_2),
            nn.ReLU(),

            nn.Linear(dim_2, dim_1),
            nn.ReLU(),

            nn.Linear(dim_1, d_features),
        )

    def forward(self, x):
        x_comp = self.encoder(x)
        x_recon = self.decoder(x_comp)
        return x_recon
