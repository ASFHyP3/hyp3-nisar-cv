import numpy as np

from nisar_cv import process


def run(stack, **kwargs):
    stats = process.WelfordCV(np.asarray(stack.shape[1:]), **kwargs)
    for layer in stack:
        stats.update(layer)
    return stats


def column(*values):
    return np.array(values, np.float32).reshape(len(values), 1, 1)


def test_cv_matches_population_std_over_mean():
    stack = np.random.default_rng(0).uniform(0.01, 0.5, (6, 5, 4)).astype(np.float32)
    expected = stack.std(axis=0) / stack.mean(axis=0)
    np.testing.assert_allclose(run(stack).cv(), expected, rtol=1e-5)


def test_constant_pixel_has_zero_cv():
    np.testing.assert_allclose(
        run(np.full((4, 2, 2), 0.1, np.float32)).cv(), 0, atol=1e-6
    )


def test_nan_zero_and_negative_samples_are_skipped():
    stats = run(column(0.1, np.nan, 0.2, 0.0, 0.3, -1.0))
    assert stats.n_valid[0, 0] == 3
    valid = np.array([0.1, 0.2, 0.3])
    np.testing.assert_allclose(stats.cv()[0, 0], valid.std() / valid.mean(), rtol=1e-5)


def test_water_mask():
    assert run(column(1, 0, 0, 0)).water_mask(0.75)[0, 0] == 1
