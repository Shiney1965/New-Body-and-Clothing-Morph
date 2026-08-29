from pathlib import Path

import numpy as np


HERE = Path(__file__).parent
np.save(
    HERE / "synthetic_body.npy",
    np.array([[-0.2, -0.2, 0.0], [0.2, -0.2, 0.0], [0.2, 0.2, 0.0], [-0.2, 0.2, 0.0]], dtype=np.float64),
)
np.save(
    HERE / "synthetic_garment.npy",
    np.array([[-0.05, -0.05, -0.01], [0.05, -0.05, -0.01], [0.0, 0.05, -0.01]], dtype=np.float64),
)
