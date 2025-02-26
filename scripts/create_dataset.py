import os
from PIL import Image
import torch
from torch.utils.data import Dataset, DataLoader
from torchvision.transforms import transforms
import random
Image.MAX_IMAGE_PIXELS = None


class CustomDataset(Dataset):
    def __init__(self, data_dir, metric, transform=None):
        self.data_dir = data_dir
        self.transform = transform
        self.image_files = os.listdir(data_dir)
        self.metric = metric

    def __len__(self):
        return len(self.image_files)

    def __getitem__(self, index):
        image_name = self.image_files[index]
        image_path = os.path.join(self.data_dir, image_name)

        # Load the image
        image = Image.open(image_path)

        # Extract the label from the image name
        filename_parts = image_name.split("_")
        if self.metric == 'density':
            label = float(filename_parts[-3])
        if self.metric == 'mhi':
            label = int(filename_parts[-2])
        if self.metric == 'ed':
            label = float(filename_parts[-1].replace(".tif",""))

        # Apply transformations if provided
        image = self.transform(image)

        return image, label


def generate_dataset(metric, image_type, batch_size=16, new_width=None, new_height=None):
    
    # Define image directory, batch size, and the transformations to apply to the images based on image type
    if image_type == 'patch':
        data_dir = '../data/patches'
        transform = transforms.Compose([
            transforms.ToTensor()
        ])

    if image_type == 'resize': 
        data_dir = '../data/crops'
        transform = transforms.Compose([
            transforms.Resize((new_width, new_height)),
            transforms.ToTensor()
        ])   

    # Set a random seed for reproducibility
    random.seed(42)

    # Create an instance of the custom dataset
    dataset = CustomDataset(data_dir, metric, transform=transform)

    # Calculate the sizes for training, validation, and testing sets
    dataset_size = len(dataset)
    train_size = int(0.7 * dataset_size)
    val_size = int(0.15 * dataset_size)

    # Create random indices for splitting the dataset
    indices = list(range(dataset_size))
    random.shuffle(indices)

    # Split the dataset into training, validation, and testing sets
    train_indices = indices[:train_size]
    val_indices = indices[train_size:train_size + val_size]
    test_indices = indices[train_size + val_size:]

    # Create the training dataset
    train_dataset = torch.utils.data.Subset(dataset, train_indices)

    # Create the validation dataset
    val_dataset = torch.utils.data.Subset(dataset, val_indices)

    # Create the testing dataset
    test_dataset = torch.utils.data.Subset(dataset, test_indices)

    print("Training set size:", len(train_dataset))
    print("Validation set size:", len(val_dataset))
    print("Testing set size:", len(test_dataset))

    # Create data loaders
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size)
    test_loader = DataLoader(test_dataset, batch_size=batch_size)

    return train_dataset, val_dataset, test_dataset, train_loader, val_loader, test_loader