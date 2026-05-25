"""Prepare MNIST and Fashion-MNIST datasets as binary float format."""
import gzip, os, struct, urllib.request
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

FASHION_S3 = "http://fashion-mnist.s3-website.eu-central-1.amazonaws.com"

FASHION_FILES = {
    "train-images-idx3-ubyte.gz": ("train", "img"),
    "train-labels-idx1-ubyte.gz": ("train", "lbl"),
    "t10k-images-idx3-ubyte.gz": ("test", "img"),
    "t10k-labels-idx1-ubyte.gz": ("test", "lbl"),
}

def download(url, path):
    if not os.path.exists(path):
        print(f"Downloading {url}...")
        urllib.request.urlretrieve(url, path)

def parse_idx_images(path):
    with gzip.open(path, "rb") as f:
        magic, n, rows, cols = struct.unpack(">IIII", f.read(16))
        data = np.frombuffer(f.read(), dtype=np.uint8).reshape(n, rows * cols)
    return data.astype(np.float32) / 255.0

def parse_idx_labels(path):
    with gzip.open(path, "rb") as f:
        magic, n = struct.unpack(">II", f.read(8))
        data = np.frombuffer(f.read(), dtype=np.uint8)
    return data.astype(np.float32)

def to_binary(images, labels, name):
    n = images.shape[0]
    buf = struct.pack("i", n)
    for i in range(n):
        buf += images[i].tobytes() + struct.pack("f", float(labels[i]))
    path = os.path.join(DATA_DIR, name)
    with open(path, "wb") as f:
        f.write(buf)
    print(f"  {name}: {n} samples ({os.path.getsize(path):,} bytes)")

def prepare_fashion():
    gz_dir = os.path.join(DATA_DIR, "fashion_gz")
    os.makedirs(gz_dir, exist_ok=True)
    for fname in FASHION_FILES:
        url = f"{FASHION_S3}/{fname}"
        path = os.path.join(gz_dir, fname)
        download(url, path)

    train_img = parse_idx_images(os.path.join(gz_dir, "train-images-idx3-ubyte.gz"))
    train_lbl = parse_idx_labels(os.path.join(gz_dir, "train-labels-idx1-ubyte.gz"))
    test_img = parse_idx_images(os.path.join(gz_dir, "t10k-images-idx3-ubyte.gz"))
    test_lbl = parse_idx_labels(os.path.join(gz_dir, "t10k-labels-idx1-ubyte.gz"))
    print(f"fashion_mnist: train {train_img.shape} test {test_img.shape}")
    to_binary(train_img, train_lbl, "fashion_mnist_train.bin")
    to_binary(test_img, test_lbl, "fashion_mnist_test.bin")
    to_binary(train_img[:500], train_lbl[:500], "fashion_mnist_train_500.bin")
    to_binary(test_img[:100], test_lbl[:100], "fashion_mnist_test_100.bin")

def prepare_mnist():
    TF_MIRROR = "https://storage.googleapis.com/tensorflow/tf-keras-datasets"
    url = f"{TF_MIRROR}/mnist.npz"
    path = os.path.join(DATA_DIR, "mnist.npz")
    download(url, path)
    data = np.load(path)
    train_img = data["x_train"].astype(np.float32).reshape(-1, 784) / 255.0
    train_lbl = data["y_train"].astype(np.float32)
    test_img = data["x_test"].astype(np.float32).reshape(-1, 784) / 255.0
    test_lbl = data["y_test"].astype(np.float32)
    print(f"mnist: train {train_img.shape} test {test_img.shape}")
    to_binary(train_img, train_lbl, "mnist_train.bin")
    to_binary(test_img, test_lbl, "mnist_test.bin")
    to_binary(train_img[:100], train_lbl[:100], "mnist_train_100.bin")
    to_binary(test_img[:20], test_lbl[:20], "mnist_test_20.bin")

if __name__ == "__main__":
    prepare_mnist()
    prepare_fashion()
    print("Done!")
