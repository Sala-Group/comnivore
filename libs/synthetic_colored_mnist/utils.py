import torch
import numpy as np
from tqdm import tqdm
from mnist_tasks.generate_color_mnist import *
import matplotlib.pyplot as plt
import os
import torchvision.transforms as T
import pandas as pd

transform = {
    "background": transform_background_color,
    "full": transform_image,
    "digit": transform_digit_color,
}
random_generator = {
    "background": generate_random_digit_color,
    "full": generate_random_environment,
    "digit": generate_random_digit_color
}

def transform_image_with_env(env, loader, digits_to_store=[0,1], mode="background"):
    images = torch.zeros((1,3,28,28))
    y_true = []
    for _, (imgs, labels) in tqdm(enumerate(loader)):
        if len(digits_to_store) > 0:
            mask = np.logical_or(labels == digits_to_store[0], labels == digits_to_store[1])
            imgs = imgs[mask,:,:,:]
            labels = labels[mask]
        if mode != 'full':
            transformed_imgs = transform[mode](imgs, labels, env)
        else:
            assert type(env) == list
            env_0 = env[0]
            env_1 = env[1]
            transformed_imgs = transform["background"](imgs, labels, env_0)
            transformed_imgs = transform["digit"](transformed_imgs, labels, env_1)
        images=torch.vstack((images,transformed_imgs))
        y_true.extend(labels.detach().cpu().numpy())
    images = images[1:,:,:,:]
    y_true = torch.Tensor(y_true)
    return images, y_true

def transform_by_mode(mode, imgs, possible_color_keys):
    if mode == "background":
        transformed_imgs = color_background_random(imgs, possible_color_keys)
    elif mode == "digit":
        transformed_imgs = color_digit_random(imgs, possible_color_keys)
    elif mode == "full":
        digit_colors = np.random.choice(np.array(possible_color_keys), 2).flatten()
        # background_colors_idx = np.argwhere(possible_color_keys not in digit_colors)
        background_colors = [color_ for color_ in possible_color_keys if color_ not in digit_colors]
        transformed_imgs = color_background_random(imgs, background_colors)
        transformed_imgs = color_digit_random(transformed_imgs, digit_colors)
    return transformed_imgs

def transform_image_random(loader, possible_color_keys, digits_to_store=[0,1], mode="background"):
    images = torch.zeros((1,3,28,28))
    y_true = []
    for _, (imgs, labels) in tqdm(enumerate(loader)):
        if len(digits_to_store) > 0:
            mask = np.logical_or(labels == digits_to_store[0], labels == digits_to_store[1])
            imgs = imgs[mask,:,:,:]
            labels = labels[mask]
        transformed_imgs = transform_by_mode(mode, imgs, possible_color_keys)
        images=torch.vstack((images,transformed_imgs))
        y_true.extend(labels.detach().cpu().numpy())
    images = images[1:,:,:,:]
    y_true = torch.Tensor(y_true)
    return images, y_true

def generate_random_flip_map(digits=[0,1]):
    if len(digits) == 0:
        digits = np.arange(10)
    random_shuffle = np.copy(digits)
    np.random.shuffle(random_shuffle)
    random_mapping = {}
    for idx, digit in enumerate(digits):
        random_mapping[digit] = random_shuffle[idx]
    return random_mapping

def flip_digit_color(flip_mapping, env):
    new_mapping = {}
    for key in flip_mapping:
        new_mapping[key] = env[flip_mapping[key]]
        new_mapping[flip_mapping[key]] = env[key]
    return new_mapping

def show_random_images(images):
    random_samples = np.random.choice(np.linspace(0, images.shape[0]-1, images.shape[0], dtype=int), 10)
    random_samples = images[random_samples, :,:,:]
    nrows = 3
    fig, ax = plt.subplots(nrows, ncols=random_samples.shape[0]//nrows)
    i=0
    for row in ax:
        for col in row:
            image = random_samples[i,:,:,:]*255
            col.imshow(image.permute(1,2,0).detach().cpu().numpy().astype(np.uint8))
            i+=1
    plt.setp(plt.gcf().get_axes(), xticks=[], yticks=[]);
    plt.show()

def get_metadata(image_paths, labels, split, random, spurious_feats=None):
    metadata_ = {
        'image_path': image_paths, 
        'label': labels
    }
    metadata_['split'] = [split for i in range(len(metadata_['label']))]
    metadata_['random'] = [random for i in range(len(metadata_['label']))]
    if spurious_feats is not None:
        metadata_['spurious_feats_n'] = [spurious_feats for i in range(len(metadata_['label']))]
    return pd.DataFrame(metadata_)

def save_images(images, labels, split, save_dir):
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir)
    image_id = 0
    transform = T.ToPILImage()
    labels = labels.detach().cpu().numpy()
    image_paths = []
    for img_idx in range(images.shape[0]):
        label = labels[img_idx]
        img_tensor = images[img_idx, :, :, :]
        img_tensor = torch.squeeze(img_tensor)
        image_id += 1
        img = transform(img_tensor)
        image_path = os.path.join(save_dir, f"{label}_{split}_{image_id}.png")
        img.save(image_path)
        image_paths.append(image_path)
    return image_paths

def save_env_as_tensor(img, labels, env_num, store_dir, mode="train", suffix=""):
    if len(suffix) > 0:
        torch.save(img, os.path.join(store_dir,f"{mode}_env_{env_num}_{suffix}.pt"))
        torch.save(labels, os.path.join(store_dir,f"{mode}_labels_env_{env_num}_{suffix}.pt"))
    else:
        torch.save(img, os.path.join(store_dir,f"{mode}_env_{env_num}.pt"))
        torch.save(labels, os.path.join(store_dir,f"{mode}_labels_env_{env_num}.pt"))

def store_metadata(df, save_dir):
    df = pd.DataFrame(df)
    df.to_csv(os.path.join(save_dir,"metadata.csv"))