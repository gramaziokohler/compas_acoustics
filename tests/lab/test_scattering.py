import warnings

import numpy as np
import pytest
from compas import json_dumps
from compas import json_loads
from lab_shapes import bumped_box
from lab_shapes import flat_tile
from lab_shapes import flat_tile_with_zero_area_face
from lab_shapes import sine_tile

from compas_acoustics.lab import scattering
from compas_acoustics.lab.bands import EXTENDED_BAND_RANGE
from compas_acoustics.lab.bands import THIRD_OCTAVE_CENTRES
from compas_acoustics.lab.grids import SourceGrid
from compas_acoustics.lab.results import ScatteringResult
from compas_acoustics.lab.sample import ScatteringSample
from compas_acoustics.lab.scattering import measure_scattering
from compas_acoustics.lab.kirchhoff import KirchhoffSolver
from compas_acoustics.lab.kirchhoff import Pressures
from compas_acoustics.lab.scattering import preview_sources


class FakeSolver:
    """Identical pressures for the sample and the reference, in one batch."""

    workers = 1

    def __init__(self, **options):
        pass

    def pressures(self, sources, receivers, frequencies):
        rng = np.random.default_rng(1)
        p0 = rng.normal(size=(sources.n, len(receivers.weights), len(frequencies))) + 0j
        return Pressures(p0.copy(), p0, frequencies, {"method": "fake"})

    def solve_batches(self, sample, sources, receivers, frequencies, c, batch_size):
        yield np.arange(sources.n), self.pressures(sources, receivers, frequencies)

    def estimate_seconds(self, sample, sources, receivers, frequencies):
        return 1.0

    def warnings(self, *args):
        return []


class NanSolver(FakeSolver):
    def pressures(self, sources, receivers, frequencies):
        p = super().pressures(sources, receivers, frequencies)
        p.sample[0, 0, 0] = np.nan
        return p


def test_shapes_and_bands(monkeypatch):
    monkeypatch.setattr(scattering, "KirchhoffSolver", FakeSolver)
    r = measure_scattering(ScatteringSample.disc(flat_tile(), diameter=0.4), preset="survey")
    assert r.bands == list(THIRD_OCTAVE_CENTRES[:18]) and len(r.s_bands) == 18  # default: ISO 100-5000
    assert r.octave_bands == [125, 250, 500, 1000, 2000, 4000] and len(r.scattering_coefficients) == 7
    assert r.filled_octaves == [8000] and r.scattering_coefficients[6] == r.scattering_coefficients[5]
    assert any("8000 Hz octave was not simulated" in w for w in r.warnings)
    assert r.s_angle.shape == (13, 18) and r.polar_sample_db.shape[:2] == (13, 6)
    assert np.allclose(r.s_octaves, 0.0, atol=1e-9)  # identical pressures -> no scattering
    assert np.isclose(r.polar_reference_db.max(axis=2), 0.0).all()


def test_extended_range_simulates_8000_and_warns_beyond_iso(monkeypatch):
    monkeypatch.setattr(scattering, "KirchhoffSolver", FakeSolver)
    r = measure_scattering(ScatteringSample.disc(flat_tile(), diameter=0.4), preset="survey", band_range=EXTENDED_BAND_RANGE)
    assert r.bands[-1] == 8000 and r.octave_bands[-1] == 8000 and r.filled_octaves == []
    assert any("beyond ISO" in w for w in r.warnings)


def test_default_preset_is_standard_and_an_explicit_one_overrides_it(monkeypatch):
    monkeypatch.setattr(scattering, "KirchhoffSolver", FakeSolver)
    sample = ScatteringSample.disc(flat_tile(), diameter=0.4)
    assert measure_scattering(sample, band_range=(1000, 1000)).generation["preset"] == "standard"
    assert measure_scattering(sample, preset="survey", band_range=(1000, 1000)).generation["preset"] == "survey"


def test_an_unknown_solver_option_raises():
    with pytest.raises(TypeError):
        measure_scattering(ScatteringSample.disc(flat_tile(), diameter=0.4), preset="survey", band_range=(1000, 1000), n_rays=10)


def test_warnings_are_also_emitted(monkeypatch):
    monkeypatch.setattr(scattering, "KirchhoffSolver", FakeSolver)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        r = measure_scattering(ScatteringSample.disc(flat_tile(), diameter=0.4), preset="survey", band_range=(4000, 4000))
    assert "the 8000 Hz octave was not simulated; the material takes the 4000 Hz value" in r.warnings
    assert r.filled_octaves == [125, 250, 500, 1000, 2000, 8000]
    assert set(r.warnings) <= {str(w.message) for w in caught}


def test_non_finite_pressures_raise_naming_the_method(monkeypatch):
    monkeypatch.setattr(scattering, "KirchhoffSolver", NanSolver)
    with pytest.raises(RuntimeError, match="kirchhoff"):
        measure_scattering(ScatteringSample.disc(flat_tile(), diameter=0.4), preset="survey", band_range=(1000, 1000))


def test_kirchhoff_end_to_end_sine_beats_flat():
    flat = measure_scattering(ScatteringSample.disc(flat_tile(), diameter=0.4), preset="survey", band_range=(4000, 4000))
    sine = measure_scattering(ScatteringSample.disc(sine_tile(0.0708, 0.0204), diameter=0.4), preset="survey", band_range=(4000, 4000))
    assert max(flat.s_bands) < 0.05 and sine.s_bands[-1] > 0.3


def test_result_has_no_nan_with_degenerate_faces():
    tile = flat_tile_with_zero_area_face()
    r = measure_scattering(ScatteringSample.disc(tile, diameter=0.4), preset="survey", band_range=(500, 1000))
    assert np.isfinite(r.s_bands).all()


def test_result_round_trips_through_json():
    r = measure_scattering(ScatteringSample.disc(flat_tile(), diameter=0.3), preset="survey", band_range=(500, 1000))
    t = json_loads(json_dumps(r))
    assert isinstance(t, ScatteringResult) and np.allclose(t.s_angle, r.s_angle) and t.generation["method"] == "kirchhoff"
    assert t.polar_source_indices == r.polar_source_indices
    import json

    json.loads(json_dumps(r), parse_constant=lambda name: pytest.fail("not strict JSON: " + name))


def test_polar_levels_are_kept_for_the_preview_sources_only(monkeypatch):
    monkeypatch.setattr(scattering, "KirchhoffSolver", FakeSolver)
    sample = ScatteringSample.disc(flat_tile(), diameter=0.4)
    r = measure_scattering(sample, preset="standard", band_range=(1000, 1000))
    assert r.s_angle.shape[0] == 97 and len(r.polar_source_indices) == 13 and r.polar_sample_db.shape == (13, 1, len(r.receiver_directions))
    survey = SourceGrid.preset("survey")
    used = np.column_stack([r.source_colatitude, r.source_azimuth])[r.polar_source_indices]
    assert sorted(map(tuple, used)) == sorted(zip(survey.colatitude, survey.azimuth))  # "standard" holds the survey directions
    rotational = ScatteringSample.disc(flat_tile(), diameter=0.4, symmetry="rotational")
    assert preview_sources(SourceGrid.preset("fine", "rotational"), "rotational") == [0, 11, 23]  # 1.26°, 28.98°, 59.22°: nearest 0°, 30°, 60°
    assert measure_scattering(rotational, preset="standard", band_range=(1000, 1000)).polar_source_indices == [0, 3, 6]


def test_batched_kirchhoff_gives_the_unbatched_result(monkeypatch):
    sample = ScatteringSample.disc(sine_tile(0.0708, 0.0204), diameter=0.3)
    whole = measure_scattering(sample, preset="survey", band_range=(2000, 2000), workers=1)
    monkeypatch.setattr(scattering, "_BATCH_BYTES", 1)  # one source per batch
    calls = []
    original = KirchhoffSolver.solve_batches

    def spy(self, *args, **kwargs):
        calls.append(kwargs["batch_size"])
        return original(self, *args, **kwargs)

    monkeypatch.setattr(KirchhoffSolver, "solve_batches", spy)
    batched = measure_scattering(sample, preset="survey", band_range=(2000, 2000), workers=1)
    assert calls == [1]
    assert np.array_equal(batched.s_angle, whole.s_angle) and batched.s_bands == whole.s_bands
    assert np.array_equal(batched.polar_sample_db, whole.polar_sample_db) and np.array_equal(batched.polar_reference_db, whole.polar_reference_db)


class SlowSolver(FakeSolver):
    def estimate_seconds(self, sample, sources, receivers, frequencies):
        return 7200.0


def test_a_long_run_is_warned_about_before_it_starts(monkeypatch):
    monkeypatch.setattr(scattering, "KirchhoffSolver", SlowSolver)
    with pytest.warns(UserWarning, match=r"kirchhoff: this run takes about 2.0 h \(13 sources x 3 frequencies"):
        measure_scattering(ScatteringSample.disc(flat_tile(), diameter=0.4), preset="survey", band_range=(1000, 1000))


def test_classes_are_exported_from_the_package():
    import compas_acoustics

    assert compas_acoustics.ScatteringResult is ScatteringResult and compas_acoustics.ScatteringSample is ScatteringSample


def test_the_result_holds_d(monkeypatch):
    with monkeypatch.context() as patched:
        patched.setattr(scattering, "KirchhoffSolver", FakeSolver)
        same = measure_scattering(ScatteringSample.disc(flat_tile(), diameter=0.4), preset="survey")
    assert np.allclose(same.d_octaves, 0.0, atol=1e-9)  # sample == reference -> d_n = 0
    assert same.d_angle.shape == same.s_angle.shape and len(same.d_bands) == len(same.bands) and len(same.d_octaves) == len(same.octave_bands)
    sine = measure_scattering(ScatteringSample.disc(sine_tile(0.0708, 0.0204), diameter=0.4), preset="survey", band_range=(2000, 4000))
    assert np.isfinite(sine.d_angle).all()
    # d_octaves 0.0093 (2 kHz), 0.0175 (4 kHz); d_n may be negative in general (a sample less uniform than its reference)
    assert all(0.0 <= d <= 1.0 for d in sine.d_octaves) and max(sine.d_octaves) > 0.0


def test_the_reference_kind_is_recorded(monkeypatch):
    monkeypatch.setattr(scattering, "KirchhoffSolver", FakeSolver)
    proxy = ScatteringSample.as_drawn(bumped_box(), reference=bumped_box(bump=0.0))
    assert measure_scattering(proxy, preset="survey", band_range=(1000, 1000)).generation["reference"] == "proxy"
    flat = ScatteringSample.disc(flat_tile(), 0.4)
    assert measure_scattering(flat, preset="survey", band_range=(1000, 1000)).generation["reference"] == "flat"
