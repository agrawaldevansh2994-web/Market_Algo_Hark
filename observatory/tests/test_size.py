import numpy as np
import pandas as pd

from obs.size import mcap_estimate


def test_mcap_is_price_times_shares_when_known():
    px = pd.Series({"A": 100.0, "B": 50.0})
    adv = pd.Series({"A": 10.0, "B": 5.0})
    sh = pd.Series({"A": 1e6, "B": 2e6})
    mc, imp = mcap_estimate(px, adv, sh)
    assert mc["A"] == 1e8 and mc["B"] == 1e8
    assert not imp.any()


def test_missing_share_count_is_imputed_from_turnover():
    px = pd.Series({"A": 100.0, "B": 50.0, "GONE": 20.0})
    adv = pd.Series({"A": 10.0, "B": 10.0, "GONE": 4.0})
    sh = pd.Series({"A": 1e6, "B": 4e6})          # GONE delisted: no count
    mc, imp = mcap_estimate(px, adv, sh)
    ratio = np.median([1e8 / 10, 2e8 / 10])
    assert imp["GONE"] and not imp["A"]
    assert mc["GONE"] == 4.0 * ratio
