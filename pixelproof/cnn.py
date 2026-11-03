"""Small forensic CNN ("PixelNet", 74,116 trainable parameters, CPU-friendly).

Design choices (standard in image forensics):
  * a FIXED high-pass front end (3 SRM residual kernels applied to each colour channel) so the
    network looks at sensor noise and interpolation traces rather than scene content
  * truncation (TLU, clamp to [-3, 3]) of the residuals, which stabilises training
  * the raw RGB patch is concatenated so smoothness/colour cues of inpainting remain available
  * three conv stages (16-32-64 channels) + global average & max pooling + linear head (4 classes)
  * augmentations that keep forensic traces intact: flips and 90-degree rotations only
  * optional (candidate detector): wider layers (width 32), dropout, label smoothing, early stopping on the
    validation recall at the target false-alarm rate, and test-time averaging over the same 8 symmetries

The CNN is fused with the feature model (pixelproof.detector) by averaging class
probabilities; the fusion weight and the alarm threshold are chosen on the validation set.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

_K = np.array([
    [[0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 1, -2, 1, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]],          # 2nd order, horizontal
    [[0, 0, 0, 0, 0], [0, -1, 2, -1, 0], [0, 2, -4, 2, 0], [0, -1, 2, -1, 0], [0, 0, 0, 0, 0]],     # 3x3 square
    [[-1, 2, -2, 2, -1], [2, -6, 8, -6, 2], [-2, 8, -12, 8, -2], [2, -6, 8, -6, 2], [-1, 2, -2, 2, -1]],  # KV 5x5
], np.float32) / np.array([2, 4, 12], np.float32)[:, None, None]


class PixelNet(nn.Module):
    def __init__(self, n_classes: int = 4, width: int = 16, dropout: float = 0.0):
        super().__init__()
        self.drop = nn.Dropout(dropout)  # no parameters: files saved without it still load
        w = torch.from_numpy(np.repeat(_K[None], 3, 0).reshape(9, 1, 5, 5))
        self.register_buffer("srm", w)
        c = width

        def block(i, o):
            return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                                 nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

        self.b1, self.b2, self.b3 = block(12, c), block(c, 2 * c), block(2 * c, 4 * c)
        self.head = nn.Linear(8 * c, n_classes)

    def forward(self, x):  # x: (N,3,64,64) in [0,1]
        r = F.conv2d(x * 255.0, self.srm, padding=2, groups=3)
        r = torch.clamp(r, -3, 3) / 3.0
        h = torch.cat([r, x - 0.5], 1)
        h = F.max_pool2d(self.b1(h), 2)
        h = F.max_pool2d(self.b2(h), 2)
        h = self.b3(h)
        h = torch.cat([h.mean((2, 3)), h.amax((2, 3))], 1)
        return self.head(self.drop(h))


def to_tensor(imgs: np.ndarray) -> torch.Tensor:
    if not imgs.flags.writeable:  # torch warns on read-only buffers (e.g. decoded from bytes)
        imgs = imgs.copy()
    return torch.from_numpy(imgs).permute(0, 3, 1, 2).float() / 255.0


def augment(x: torch.Tensor) -> torch.Tensor:
    if torch.rand(1) < 0.5:
        x = x.flip(3)
    if torch.rand(1) < 0.5:
        x = x.flip(2)
    k = int(torch.randint(0, 4, (1,)))
    return torch.rot90(x, k, (2, 3)) if k else x


def recall_at_fpr(P: np.ndarray, labels: np.ndarray, clean_authentic: np.ndarray, target_fpr: float = 0.05) -> float:
    """Detection rate when the alarm threshold allows `target_fpr` false alarms on clean authentic patches:
    the operating point the product actually uses (detector.py), so it is the right thing to select on."""
    s = 1.0 - P[:, 0]
    thr = float(np.quantile(s[clean_authentic], 1 - target_fpr))
    return float((s[labels != 0] >= thr).mean())


def train(imgs, labels, val_imgs, val_labels, epochs=12, batch=128, lr=2e-3, seed=0, log=print, width=16,
          dropout=0.0, label_smoothing=0.0, select="acc", val_clean_authentic=None, target_fpr=0.05, patience=None):
    """select="acc" keeps the epoch with the best validation accuracy (how the shipped model was trained);
    select="recall" keeps the best validation recall at `target_fpr` (needs val_clean_authentic, a boolean mask of the
    clean authentic validation patches). patience: stop after that many epochs without improvement."""
    if select == "recall" and val_clean_authentic is None:
        raise ValueError("select='recall' needs val_clean_authentic")
    torch.manual_seed(seed)
    np.random.seed(seed)
    net = PixelNet(width=width, dropout=dropout)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    steps = epochs * int(np.ceil(len(imgs) / batch))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps)
    y = torch.from_numpy(labels.astype(np.int64))
    best, best_state, best_ep = -1.0, None, 0
    for ep in range(epochs):
        net.train()
        perm = np.random.permutation(len(imgs))
        tot = 0.0
        for i in range(0, len(perm), batch):
            idx = perm[i:i + batch]
            xb = augment(to_tensor(imgs[idx]))
            loss = F.cross_entropy(net(xb), y[idx], label_smoothing=label_smoothing)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tot += loss.item() * len(idx)
        P = predict_proba(net, val_imgs)
        acc = float((P.argmax(1) == val_labels).mean())
        msg = f"epoch {ep + 1}/{epochs} loss {tot / len(imgs):.4f} val_acc {acc:.4f}"
        score = acc
        if val_clean_authentic is not None:
            rec = recall_at_fpr(P, val_labels, val_clean_authentic, target_fpr)
            msg += f" val_recall@{target_fpr:.0%} {rec:.4f}"
            if select == "recall":
                score = rec
        log(msg)
        if score > best:
            best, best_ep, best_state = score, ep, {k: v.clone() for k, v in net.state_dict().items()}
        elif patience is not None and ep - best_ep >= patience:
            log(f"early stop: no improvement for {patience} epochs (best epoch {best_ep + 1})")
            break
    net.load_state_dict(best_state)
    net.eval()
    return net


def _dihedral(x: torch.Tensor, k: int) -> torch.Tensor:
    """The 8 symmetries of a square (4 rotations x optional flip): the same set used for augmentation."""
    x = x.flip(3) if k >= 4 else x
    return torch.rot90(x, k % 4, (2, 3)) if k % 4 else x


@torch.no_grad()
def predict_proba(net, imgs, batch=512, tta=False) -> np.ndarray:
    """Class probabilities. tta=True averages over the 8 flips/rotations (test-time augmentation): the network was
    trained on those symmetries, so averaging removes orientation noise; it costs 8 forward passes."""
    net.eval()
    out = []
    for i in range(0, len(imgs), batch):
        x = to_tensor(imgs[i:i + batch])
        if tta:
            p = sum(F.softmax(net(_dihedral(x, k)), 1) for k in range(8)) / 8
        else:
            p = F.softmax(net(x), 1)
        out.append(p.numpy())
    return np.concatenate(out) if out else np.zeros((0, 4), np.float32)


def save(net, path):
    torch.save(net.state_dict(), path)


def load(path) -> PixelNet:
    state = torch.load(path, map_location="cpu", weights_only=True)
    net = PixelNet(width=int(state["b1.0.weight"].shape[0]))  # width read from the file (16 for the shipped model)
    net.load_state_dict(state)
    net.eval()
    return net
