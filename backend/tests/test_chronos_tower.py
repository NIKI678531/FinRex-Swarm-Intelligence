import unittest

import pandas as pd
import torch

from backend.app.quant.models import tower_chronos


class ChronosTowerTest(unittest.TestCase):
    def test_predict_supports_inputs_keyword_api(self):
        class FakePipe:
            def predict_quantiles(self, *, inputs, prediction_length, quantile_levels):
                self.inputs = inputs
                return torch.tensor([[[9.0, 10.0, 11.0], [10.0, 11.0, 12.0]]]), torch.tensor([[10.0, 11.0]])

        fake = FakePipe()
        original = tower_chronos._load_pipeline
        tower_chronos._load_pipeline = lambda: fake
        try:
            out = tower_chronos.ChronosBoltTower().predict(pd.Series(range(40, 80)), horizon=2)
        finally:
            tower_chronos._load_pipeline = original

        self.assertIsNotNone(out)
        self.assertEqual(out["p10"], 10.0)
        self.assertEqual(out["p50"], 11.0)
        self.assertEqual(out["p90"], 12.0)
        self.assertEqual(out["horizon"], 2)


if __name__ == "__main__":
    unittest.main()
