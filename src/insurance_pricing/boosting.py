"""Histogram boosting with train-only categorical codes and proper likelihoods."""

from dataclasses import dataclass
import os
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_gamma_deviance, mean_poisson_deviance
from sklearn.preprocessing import OrdinalEncoder
from threadpoolctl import threadpool_limits

CATEGORY_FEATURES = ["Area", "VehBrand", "VehGas", "Region"]
NUMBER_FEATURES = ["VehPower", "VehAge", "DrivAge", "BonusMalus", "log_density"]
BOOST_FEATURES = CATEGORY_FEATURES + NUMBER_FEATURES


@dataclass
class BoostBundle:
    encoder: OrdinalEncoder
    models: dict
    config: dict
    selected: dict
    severity_cap: float

    def transform(self, frame):
        if frame[BOOST_FEATURES].isna().any().any():
            raise ValueError("Missing boosting rating features")
        numeric = frame[NUMBER_FEATURES].to_numpy(dtype=float)
        if not np.isfinite(numeric).all():
            raise ValueError("Non-finite boosting rating features")
        categories = self.encoder.transform(frame[CATEGORY_FEATURES].astype(str))
        return np.column_stack([categories, numeric])

    def predict(self, frame):
        x = self.transform(frame)
        output = pd.DataFrame(index=frame.index)
        with threadpool_limits(limits=self.config["threads"]):
            for name, model in self.models.items():
                output[name] = model.predict(x)
        output["pure_premium"] = output.frequency * output.severity
        if "source_frequency" in output:
            output["source_count_premium"] = output.source_frequency * output.severity
        if "capped_severity" in output:
            output["capped_severity_premium"] = output.frequency * output.capped_severity
        if not np.isfinite(output.to_numpy()).all() or (output <= 0).any().any():
            raise ValueError("Boosting predictions must be positive finite values")
        return output


def new_model(config, candidate, loss):
    return HistGradientBoostingRegressor(
        loss=loss, learning_rate=config["learning_rate"],
        l2_regularization=config["l2_regularization"], max_bins=config["max_bins"],
        categorical_features=[True] * len(CATEGORY_FEATURES) + [False] * len(NUMBER_FEATURES),
        early_stopping=False, random_state=config["seed"], **candidate,
    )


def tune_boost(train_p, train_c, valid_p, valid_c, config):
    if not train_p.split.eq("train").all() or not train_c.split.eq("train").all() or not valid_p.split.eq("validation").all() or not valid_c.split.eq("validation").all():
        raise ValueError("Tuning accepts training and validation partitions only")
    if set(train_p.IDpol) & set(valid_p.IDpol):
        raise ValueError("Overlapping training/validation policy IDs")
    if config["calibration"] != "none" or config["early_stopping"] is not False:
        raise ValueError("This predeclared search uses no calibration or automatic early stopping")
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(config["threads"]))
    encoder = OrdinalEncoder(handle_unknown="error", dtype=np.float64)
    encoder.fit(train_p[CATEGORY_FEATURES].astype(str))
    if any(len(levels) > config["max_bins"] for levels in encoder.categories_):
        raise ValueError("Category levels exceed histogram max_bins")
    cap = float(np.quantile(train_c.ClaimAmount, config["severity_cap_quantile"]))
    bundle = BoostBundle(encoder, {}, config.copy(), {}, cap)
    xp, xc = bundle.transform(train_p), bundle.transform(train_c)
    vp, vc = bundle.transform(valid_p), bundle.transform(valid_c)
    rows = []
    with threadpool_limits(limits=config["threads"]):
        for family, loss, train_x, target, weights, valid_x, valid_y, valid_weights, metric in [
            ("frequency", "poisson", xp, train_p.recorded_claim_count / train_p.Exposure, train_p.Exposure, vp, valid_p.recorded_claim_count / valid_p.Exposure, valid_p.Exposure, mean_poisson_deviance),
            ("severity", "gamma", xc, train_c.ClaimAmount, None, vc, valid_c.ClaimAmount, None, mean_gamma_deviance),
        ]:
            fitted = []
            for k, candidate in enumerate(config[f"{family}_candidates"]):
                start = time.perf_counter()
                model = new_model(config, candidate, loss).fit(train_x, target, sample_weight=weights)
                prediction = model.predict(valid_x)
                score = float(metric(valid_y, prediction, sample_weight=valid_weights))
                rows.append({"family": family, "candidate": k, **candidate, "validation_deviance": score, "fit_seconds": time.perf_counter() - start, "selected": False})
                fitted.append(model)
                print(f"{family} candidate {k}: validation deviance {score:.6f}", flush=True)
            family_rows = [row for row in rows if row["family"] == family]
            best = min(family_rows, key=lambda row: (row["validation_deviance"], row["candidate"]))
            best["selected"] = True
            bundle.models[family] = fitted[best["candidate"]]
            bundle.selected[family] = config[f"{family}_candidates"][best["candidate"]].copy()
        # Sensitivities use selected hyperparameters, with no separate retuning.
        bundle.models["source_frequency"] = new_model(config, bundle.selected["frequency"], "poisson").fit(xp, train_p.source_claim_count / train_p.Exposure, sample_weight=train_p.Exposure)
        bundle.models["capped_severity"] = new_model(config, bundle.selected["severity"], "gamma").fit(xc, np.minimum(train_c.ClaimAmount, cap))
    return bundle, pd.DataFrame(rows)
