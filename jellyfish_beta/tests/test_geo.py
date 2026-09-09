import numpy as np

from jellymru.geo import angular_difference, onshore_component, signed_square


def test_angular_difference_wraps():
    assert angular_difference(10, 350) == 20
    assert angular_difference(350, 10) == -20
    assert abs(angular_difference(180, 0)) == 180


def test_wind_from_facing_direction_is_fully_onshore():
    # Beach faces east (90). Wind FROM the east blows onto it.
    assert np.isclose(onshore_component(8.0, 90, 90), 8.0)
    # Wind FROM the west is fully offshore.
    assert np.isclose(onshore_component(8.0, 270, 90), -8.0)
    # Alongshore wind contributes nothing.
    assert np.isclose(onshore_component(8.0, 0, 90), 0.0)


def test_current_uses_to_convention():
    # Beach faces east. A current flowing TOWARD the west (270) hits the beach.
    assert np.isclose(onshore_component(0.5, 270, 90, convention="to"), 0.5)
    assert np.isclose(onshore_component(0.5, 90, 90, convention="to"), -0.5)


def test_vectorised_with_scalar_facing():
    out = onshore_component([5, 5, 5], [120, 300, 30], 120)
    assert np.allclose(out, [5, -5, 0], atol=1e-9)


def test_signed_square_keeps_sign():
    assert np.allclose(signed_square([-3, 0, 2]), [-9, 0, 4])
