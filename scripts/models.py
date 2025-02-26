import torch
import torch.nn as nn
import torchvision


class AutoEncoder(nn.Module):
    """
    AutoEncoder that uses a pretrained model as the encoder.

    Inputs:
        latent_dim: int with the dimension of the latent space
        encoder_arch: string with the name of the pretrained model
        encoder_lock_weights: bool to lock the weights of the pretrained model
        decoder_layers_per_block: list with the number of layers per block
        denoising : bool with autoencoder is denoising
    """

    def __init__(
        self,
        latent_dim,
        encoder_arch="vgg16",
        encoder_lock_weights=True,
        decoder_layers_per_block=[2, 2, 3, 3, 3],
        denoising=False,
    ):
        super(AutoEncoder, self).__init__()
        self.denoising = denoising
        self.encoder = PetrainedEncoder(latent_dim, encoder_arch, encoder_lock_weights)
        self.decoder = Decoder(latent_dim, decoder_layers_per_block, encoder_arch)

    def forward(self, x):
        if self.denoising:
            x = x + torch.normal(0, 0.1, size=x.shape, device=x.device)
        out = self.encoder(x)
        out = self.decoder(out)
        return out


class PetrainedEncoder(nn.Module):
    """
    Convolutional Encoder that uses a pretrained model as a base.
    It removes the last two layers and add two linear layers to generate the latent space.
    The pretrained model can be one of the following: vgg16, vgg19, resnet50, resnet152

    Inputs:
        latent_dim: int with the dimension of the latent space
        arch: string with the name of the pretrained model
        lock_weights: bool to lock the weights of the pretrained model
    """

    def __init__(self, latent_dim, arch="vgg16", lock_weights=True):
        super(PetrainedEncoder, self).__init__()
        assert arch in [
            "vgg16",
            "vgg16_small_patch",
            "vgg19",
            "resnet50",
            "resnet50_small_patch",
            "resnet152",
        ]
        self.latent_dim = latent_dim
        self.arch = arch
        self._get_model()
        if lock_weights:
            self.lock_weights()

    def _get_model(self):
        if self.arch == "vgg16" or self.arch == "vgg16_small_patch":
            self.pretrained_model = torchvision.models.vgg16(weights="DEFAULT")
            if self.arch == "vgg16_small_patch":
                self.pretrained_model.features[4] = nn.Identity()
            self.pretrained_model = nn.Sequential(
                *list(self.pretrained_model.children())[:-1]
            )
            self.extended_model = nn.Sequential(
                nn.Conv2d(512, 256, kernel_size=3, stride=1, padding=0),
                nn.ReLU(),
                nn.Conv2d(256, 32, kernel_size=3, stride=1, padding=0),
                nn.ReLU(),
                nn.Flatten(1, -1),
                nn.Linear(32 * 3 * 3, 256),
                nn.ReLU(),
                nn.Linear(256, self.latent_dim),
            )
        elif self.arch == "vgg19":
            self.pretrained_model = torchvision.models.vgg19(weights="DEFAULT")
            self.pretrained_model = nn.Sequential(
                *list(self.pretrained_model.children())[:-1]
            )
            self.extended_model = nn.Sequential(
                nn.Conv2d(512, 256, kernel_size=3, stride=1, padding=0),
                nn.ReLU(),
                nn.Conv2d(256, 32, kernel_size=3, stride=1, padding=0),
                nn.ReLU(),
                nn.Flatten(1, -1),
                nn.Linear(32 * 3 * 3, 256),
                nn.ReLU(),
                nn.Linear(256, self.latent_dim),
            )

        elif self.arch == "resnet50" or self.arch == "resnet50_small_patch":
            self.pretrained_model = torchvision.models.resnet50(weights="DEFAULT")
            if self.arch == "resnet50_small_patch":
                self.pretrained_model.conv1.stride = (1, 1)
            self.pretrained_model = nn.Sequential(
                *list(self.pretrained_model.children())[:-2]
            )
            self.extended_model = nn.Sequential(
                nn.Conv2d(2048, 512, kernel_size=3, stride=1, padding=1),
                nn.ReLU(),
                nn.Conv2d(512, 256, kernel_size=3, stride=1, padding=0),
                nn.ReLU(),
                nn.Conv2d(256, 32, kernel_size=3, stride=1, padding=0),
                nn.ReLU(),
                nn.Flatten(1, -1),
                nn.Linear(32 * 3 * 3, 256),
                nn.ReLU(),
                nn.Linear(256, self.latent_dim),
            )
        elif self.arch == "resnet152":
            self.pretrained_model = torchvision.models.resnet152(weights="DEFAULT")
            self.pretrained_model = nn.Sequential(
                *list(self.pretrained_model.children())[:-2]
            )
            self.extended_model = nn.Sequential(
                nn.Conv2d(2048, 512, kernel_size=3, stride=1, padding=1),
                nn.ReLU(),
                nn.Conv2d(512, 256, kernel_size=3, stride=1, padding=0),
                nn.ReLU(),
                nn.Conv2d(256, 32, kernel_size=3, stride=1, padding=0),
                nn.ReLU(),
                nn.Flatten(1, -1),
                nn.Linear(32 * 3 * 3, 256),
                nn.ReLU(),
                nn.Linear(256, self.latent_dim),
            )

    def lock_weights(self):
        for param in self.pretrained_model.parameters():
            param.requires_grad = False

    def unlock_weights(self):
        for param in self.pretrained_model.parameters():
            param.requires_grad = True

    def forward(self, x):
        x = self.pretrained_model(x)
        x = self.extended_model(x)
        return x


class Decoder(nn.Module):
    """
    Convolutional Decoder. It recieves an 1 dimensional vector, reshape into an image
    and apply convolutional layers to generate the image of size 224x224x3.

    Code adpted from https://github.com/Horizon2333/imagenet-autoencoder/blob/main/models/vgg.py

    Inputs:
        latent_dim: int with the dimension of the latent space !!! (must be a multiple of 49) !!!
        latent_dim_channels: int with the number of channels of the latent space (must be 128, 256 or 512)
        layers_per_block: list with the number of layers per block (must have 5 elements)
        enable_bn: bool to enable batch normalization
    """

    def __init__(
        self,
        latent_dim,
        layers_per_block=[2, 2, 3, 3, 3],
        encoder_arch="resnet50",
    ):
        super(Decoder, self).__init__()
        # assert latent_dim % 49 == 0
        assert len(layers_per_block) == 5
        self.latent_dim = latent_dim
        self.decoder = []
        self.decoder += [
            nn.Linear(latent_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 7 * 7 * 8),
            nn.ReLU(),
            nn.Unflatten(dim=1, unflattened_size=(8, 7, 7)),
        ]

        if "small_patch" in encoder_arch:
            n_blocks = 4
            blocks_in_channel = [8, 128, 256, 16]
            blocks_out_channel = [128, 256, 16, 3]
        else:
            n_blocks = 5
            blocks_in_channel = [8, 128, 512, 128, 8]
            blocks_out_channel = [128, 512, 128, 8, 3]
        for b in range(n_blocks):
            self.decoder.append(
                nn.ConvTranspose2d(
                    blocks_in_channel[b],
                    blocks_out_channel[b],
                    kernel_size=3,
                    stride=2,
                    padding=1,
                    output_padding=1,  # if b == 0 else 0,
                )
            )
            self.decoder.append(nn.BatchNorm2d(blocks_out_channel[b]))
            self.decoder.append(nn.ReLU(True))
            for layer in range(layers_per_block[b] - 1):
                self.decoder.append(
                    nn.Conv2d(
                        blocks_out_channel[b],
                        blocks_out_channel[b],
                        kernel_size=3,
                        stride=1,
                        padding=1,
                    )
                )
                self.decoder.append(nn.ReLU(True))

        self.decoder.append(nn.Conv2d(3, 3, kernel_size=3, stride=1, padding=1))
        self.decoder.append(nn.Sigmoid())
        self.decoder = nn.Sequential(*self.decoder)

    def forward(self, x):
        return self.decoder(x)


class DEC(nn.Module):
    def __init__(
        self, n_clusters, embedding_dim, encoder, cluster_centers=None, alpha=1.0
    ):
        """
        Module which holds all the moving parts of the DEC algorithm, as described in
        Xie/Girshick/Farhadi; this includes the AutoEncoder stage and the ClusterAssignment stage.

        Inputs:
            n_clusters: int, number of clusters
            embedding_dim, encoder part of the AutoEncoder
            cluster_centers: torch.tensor, shape (n_clusters, embedding_dim), initial cluster centers
            alpha: float, parameter of the t-distribution
        """
        super(DEC, self).__init__()
        self.encoder = encoder
        self.embedding_dim = embedding_dim
        self.cluster_number = n_clusters
        self.alpha = alpha
        self.assignment = ClusterAssignment(
            n_clusters, embedding_dim, alpha, cluster_centers
        )

    def forward(self, batch):
        """
        Compute the cluster assignment using the ClusterAssignment after running the batch
        through the encoder part of the associated AutoEncoder module.

        Inputs:
            batch: torch.tensor, shape (batch_size, embedding_dim)

        Outputs:
            torch.tensor, shape (batch_size, n_clusters)
        """
        return self.assignment(self.encoder(batch))

    def centroids_distance(self, batch):
        return self.assignment.centroids_distance(self.encoder(batch))


class ClusterAssignment(nn.Module):
    def __init__(
        self,
        n_clusters,
        embedding_dim,
        alpha=1,
        cluster_centers=None,
    ):
        """
        Module to handle the soft assignment, for a description see in 3.1.1. in Xie/Girshick/Farhadi,
        where the Student's t-distribution is used measure similarity between feature vector and each
        cluster centroid.

        Inputs:
            n_clusters - int, number of clusters
            embedding_dimension - int, dimension of the embedding
            alpha - float, parameter of the t-distribution
            cluster_centers - torch.tensor, shape (n_clusters, embedding_size)

        """
        super(ClusterAssignment, self).__init__()
        self.embedding_dim = embedding_dim
        self.n_clusters = n_clusters
        self.alpha = alpha
        if cluster_centers is None:
            initial_cluster_centers = torch.zeros(
                self.n_clusters, self.embedding_dim, dtype=torch.float
            )
            nn.init.xavier_uniform_(initial_cluster_centers)
        else:
            initial_cluster_centers = cluster_centers
        self.cluster_centers = nn.Parameter(initial_cluster_centers)

    def forward(self, batch):
        """
        Compute the soft assignment for a batch of feature vectors, returning a batch of assignments
        for each cluster.

        Inputs:
            batch - torch.tensor, shape (batch_size, embedding_size)

        Outputs:
            torch.tensor, shape (batch_size, n_clusters)
        """
        norm_squared = torch.sum((batch.unsqueeze(1) - self.cluster_centers) ** 2, 2)
        numerator = 1.0 / (1.0 + (norm_squared / self.alpha))
        power = float(self.alpha + 1) / 2
        numerator = numerator**power
        return numerator / torch.sum(numerator, dim=1, keepdim=True)

    def centroids_distance(self, batch):
        return torch.sum((batch.unsqueeze(1) - self.cluster_centers) ** 2, 2)


def target_distribution(batch):
    """
    Compute the target distribution p_ij, given the batch (q_ij), as in 3.1.3 Equation 3 of
    Xie/Girshick/Farhadi; this is used the KL-divergence loss function.

    Inputs:
        batch - [batch size, number of clusters] tensor of cluster assigments

    Outputs:
        [batch size, number of clusters] tensor of target distribution
    """
    weight = (batch**2) / torch.sum(batch, 0)
    return (weight.t() / torch.sum(weight, 1)).t()


class DenoisingAutoEncoder(nn.Module):
    def __init__(self, latent_dim, layers_per_block):
        super(DenoisingAutoEncoder, self).__init__()
        n_blocks = 5

        # setting encoder
        self.encoder = []
        blocks_in_channel = [3, 8, 64, 128, 64]
        blocks_out_channel = [8, 64, 128, 64, 8]

        for b in range(n_blocks):
            self.encoder += [
                nn.Conv2d(
                    blocks_in_channel[b],
                    blocks_out_channel[b],
                    kernel_size=3,
                    stride=2,
                    padding=1,
                ),
                nn.BatchNorm2d(blocks_out_channel[b]),
                nn.ReLU(True),
            ]

            for layer in range(layers_per_block[b] - 1):
                self.encoder += [
                    nn.Conv2d(
                        blocks_out_channel[b],
                        blocks_out_channel[b],
                        kernel_size=3,
                        stride=1,
                        padding=1,
                    ),
                    nn.ReLU(True),
                ]

        self.encoder += [
            nn.Flatten(1),
            nn.Linear(8 * 7 * 7, 256),
            nn.ReLU(),
            nn.Linear(256, latent_dim),
        ]
        self.encoder = nn.Sequential(*self.encoder)

        # setting decoder
        self.decoder = []
        self.decoder += [
            nn.Linear(latent_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 7 * 7 * 8),
            nn.ReLU(),
            nn.Unflatten(dim=1, unflattened_size=(8, 7, 7)),
        ]

        blocks_in_channel = [8, 64, 128, 64, 8]
        blocks_out_channel = [64, 128, 64, 8, 3]
        for b in range(n_blocks):
            self.decoder.append(
                nn.ConvTranspose2d(
                    blocks_in_channel[b],
                    blocks_out_channel[b],
                    kernel_size=3,
                    stride=2,
                    padding=1,
                    output_padding=1,  # if b == 0 else 0,
                )
            )
            self.decoder.append(nn.BatchNorm2d(blocks_out_channel[b]))
            self.decoder.append(nn.ReLU(True))
            for layer in range(layers_per_block[b] - 1):
                self.decoder.append(
                    nn.Conv2d(
                        blocks_out_channel[b],
                        blocks_out_channel[b],
                        kernel_size=3,
                        stride=1,
                        padding=1,
                    )
                )
                self.decoder.append(nn.ReLU(True))

        self.decoder.append(nn.Conv2d(3, 3, kernel_size=3, stride=1, padding=1))
        self.decoder.append(nn.Sigmoid())
        self.decoder = nn.Sequential(*self.decoder)

    def forward(self, x):
        x_noisy = x + torch.normal(0, 0.1, size=x.shape, device=x.device)
        out = self.encoder(x_noisy)
        out = self.decoder(out)
        return out


class AutoEncoderResnetExtractor(nn.Module):
    def __init__(self, dims, denoising = False):
        super(AutoEncoderResnetExtractor, self).__init__()
        self.latent_dim = dims[-1]
        self.denoising = denoising
        self.feature_extractor = torchvision.models.resnet50(weights="DEFAULT")
        self.feature_extractor.conv1.stride = (1, 1)
        self.feature_extractor.fc = torch.nn.Identity()
        for param in self.feature_extractor.parameters():
            param.requires_grad = False

        self.fc = []
        for i in range(len(dims) - 1):
            self.fc += [
                nn.Linear(dims[i], dims[i + 1]),
                nn.ReLU(),
            ]
        self.fc = self.fc[:-1]
        self.fc = nn.Sequential(*self.fc)
        
        self.encoder = nn.Sequential(
            self.feature_extractor,
            self.fc,
        )

        self.decoder = []
        for i in range(len(dims) - 1, 0, -1):
            self.decoder += [
                nn.Linear(dims[i], dims[i - 1]),
                nn.ReLU(),
            ]
        self.decoder = self.decoder[:-1]
        self.decoder = nn.Sequential(*self.decoder)

    def forward(self, x):
        if self.denoising:
            x = x + torch.normal(0, 0.1, size=x.shape, device=x.device)
        features = self.feature_extractor(x)
        x = self.fc(features)
        x = self.decoder(x)
        return features, x
