"""Virtual free-field scattering measurement of a sample (ISO 17497-2; Heimes & Vorländer 2025).

The pipeline of :func:`measure_scattering`: plane waves from a source grid onto the sample and its reference (:mod:`.kirchhoff`), the
pressures on a receiver hemisphere, the correlation coefficient per direction and frequency (Heimes & Vorländer eq. 3), its mean per
one-third-octave band (eq. 11), the Paris random-incidence average, and octave values (ISO 354 §8.3, ISO 11654) for the material.
"""

import warnings as _warnings

import numpy as np

from .bands import ISO_BAND_RANGE
from .bands import band_average
from .bands import fill_octaves
from .bands import fold_to_octaves
from .bands import simulation_frequencies
from .bands import third_octave_centres
from .coefficients import diffusion_coefficient
from .coefficients import normalised_diffusion
from .coefficients import random_incidence
from .coefficients import scattering_freefield
from .grids import ReceiverGrid
from .grids import SourceGrid
from .grids import receiver_spacing
from .kirchhoff import KirchhoffSolver
from .results import ScatteringResult

__all__ = ["measure_scattering", "preview_sources"]

_ISO_TOP = 5000  # Hz, the highest band of ISO 354 and ISO 17497-1/-2
_BEYOND_ISO = "bands above 5000 Hz are beyond ISO 354 and ISO 17497 (100-5000 Hz)"
_FILLED = "the {f} Hz octave was not simulated; the material takes the {g} Hz value"
_FLOOR_DB = -300.0  # the level given where |p|² is 0 (log10(0))
_BATCH_BYTES = 512 * 2**20  # the pressures of a source batch (both bodies); the reduction's temporaries take about as much again
_LONG_RUN = 600.0  # s: a run estimated longer than this is warned about before it starts
_SLOW = (
    "kirchhoff: this run takes about {time} ({sources} sources x {frequencies} frequencies x {receivers} receivers x {faces} faces, {workers} "
    "workers); the 'survey' preset, a narrower band_range or a smaller diameter is faster"
)


def _duration(seconds):
    if seconds < 3600:
        return "{:.0f} min".format(seconds / 60)
    return "{:.1f} h".format(seconds / 3600)


def preview_sources(sources, symmetry="none"):
    """The sources whose polar levels a result keeps: those nearest the ISO 17497-2 Table 1 directions (the ``"survey"`` preset).

    Parameters
    ----------
    sources : :class:`compas_acoustics.lab.grids.SourceGrid`
        The sources used.
    symmetry : {"none", "rotational"}, optional
        The sample's symmetry, which thins the survey directions as it thins the presets.

    Returns
    -------
    list of int
        Indices into ``sources``, ascending and without repeats: at most 13.
    """
    survey = SourceGrid.preset("survey", symmetry).directions
    nearest = np.argmax(survey @ np.asarray(sources.directions, dtype=float).T, axis=1)
    return sorted(set(int(i) for i in nearest))


def _polar_levels(p_sample, p_reference, nominal):
    """Levels per source, simulated octave and receiver in dB, relative to the reference's maximum for the same source and octave.

    The level of an octave is the mean of |p|² over the simulation frequencies inside it: the mean per band of its three frequencies
    (Heimes & Vorländer eq. 11), then the mean of the bands inside the octave (ISO 354 §8.3), which is the same with three per band.

    Returns
    -------
    tuple of numpy.ndarray
        ``(sample_db, reference_db)``, float32, shape (n_sources, n_octaves, n_receivers).
    """
    energies = []
    for p in (p_sample, p_reference):
        _, octave = fold_to_octaves(band_average(np.abs(p) ** 2), nominal)  # (n_src, n_rec, n_oct)
        energies.append(np.moveaxis(octave, -1, 1))
    peak = energies[1].max(axis=-1, keepdims=True)
    peak = np.where(peak > 0, peak, 1.0)
    out = []
    for energy in energies:
        ratio = energy / peak
        db = 10.0 * np.log10(np.where(ratio > 0, ratio, 1.0))
        out.append(np.where(ratio > 0, np.maximum(db, _FLOOR_DB), _FLOOR_DB).astype(np.float32))
    return out[0], out[1]


def measure_scattering(sample, preset="standard", band_range=ISO_BAND_RANGE, air=None, name=None, **solver_options) -> ScatteringResult:
    """Measure the scattering and diffusion coefficients of a sample in a virtual free field (ISO 17497-2; Heimes & Vorländer 2025).

    Physical optics (:class:`~compas_acoustics.lab.kirchhoff.KirchhoffSolver`) gives the free-field pressures of the sample and its
    reference on a receiver hemisphere of radius ``10·d``, at receiver spacing ``min(5°, 50·λ_min/d)`` (ISO 17497-2 §6.2.2, Heimes eq. 6).
    The correlation coefficient of the two (Mommertz 2000; Heimes & Vorländer eq. 3) is computed per source direction and frequency,
    averaged over the three frequencies of each one-third-octave band (eq. 11), weighted over the sources with the Paris weights for
    random incidence, and averaged per octave (ISO 354 §8.3, ISO 11654).

    The normalised diffusion coefficient ``d_n = (d − d_ref)/(1 − d_ref)`` comes with it: d from ISO 17497-2 eq. 6 on |p|² at the
    receivers weighted by their solid angles, per frequency, then averaged per band, with the same random incidence and octaves as s
    (``result.d_angle``, ``d_bands``, ``d_octaves``).

    The sources run batch by batch, each batch reduced to its correlation coefficients before the next, so the pressures of all sources
    are never held at once (a batch holds at most 512 MB of them). The polar levels are kept only for the preview sources
    (:func:`preview_sources`: the sources nearest to the 13 directions of ISO 17497-2 Table 1), listed in ``result.polar_source_indices``.
    A run estimated longer than 10 minutes is warned about before it starts
    (:meth:`~compas_acoustics.lab.kirchhoff.KirchhoffSolver.estimate_seconds`): the ``"fine"`` preset on a 0.8 m disc takes about
    50 minutes on 14 cores, the default ``"standard"`` about 5.

    Parameters
    ----------
    sample : :class:`compas_acoustics.lab.sample.ScatteringSample`
    preset : {"survey", "standard", "fine"}, optional
        The source grid.
    band_range : tuple of float, optional
        The nominal one-third-octave centres simulated, inclusive: ``ISO_BAND_RANGE`` (100-5000 Hz, ISO 17497-1/-2 §5) by default,
        ``EXTENDED_BAND_RANGE`` for the extension to 8 kHz beyond the standards.
    air : :class:`compas_acoustics.room.AirConditions`, optional
        Gives the speed of sound; the default air by default.
    name : str, optional
        The result's name; the sample's by default.
    **solver_options
        Passed to :class:`~compas_acoustics.lab.kirchhoff.KirchhoffSolver`: ``shadowing``, ``chunk``, ``workers``.

    Returns
    -------
    :class:`compas_acoustics.lab.results.ScatteringResult`

    Raises
    ------
    ValueError
        If the preset or band range is invalid.
    TypeError
        If a solver option is not one of the solver's.
    RuntimeError
        If the solver returned non-finite pressures.
    """
    if air is None:
        from compas_acoustics.room import AirConditions

        air = AirConditions()
    c = float(air.speed_of_sound)

    nominal, exact = third_octave_centres(band_range)
    sources = SourceGrid.preset(preset, sample.symmetry)
    preview = preview_sources(sources, sample.symmetry)
    frequencies = simulation_frequencies(band_range)
    receivers = ReceiverGrid.hemisphere(receiver_spacing(sample.diameter, frequencies.max(), c), radius=10.0 * sample.diameter)
    solver = KirchhoffSolver(**solver_options)

    seconds = solver.estimate_seconds(sample, sources, receivers, frequencies)
    if seconds > _LONG_RUN:
        _warnings.warn(
            _SLOW.format(
                time=_duration(seconds),
                sources=sources.n,
                frequencies=len(frequencies),
                receivers=len(receivers.weights),
                faces=sample.sample.number_of_faces() + sample.reference.number_of_faces(),
                workers=min(solver.workers, sources.n),
            ),
            stacklevel=2,
        )

    octaves, _ = fold_to_octaves(np.zeros(len(nominal)), nominal)
    s_f = np.empty((sources.n, len(frequencies)))
    d_f = np.empty_like(s_f)
    polar_sample = np.empty((len(preview), len(octaves), len(receivers.weights)), dtype=np.float32)
    polar_reference = np.empty_like(polar_sample)
    solver_generation = {}
    per_source = 2 * len(receivers.weights) * len(frequencies) * np.dtype(complex).itemsize
    batches = solver.solve_batches(sample, sources, receivers, frequencies, c, batch_size=max(1, int(_BATCH_BYTES // per_source)))
    try:
        for indices, pressures in batches:
            if not (np.isfinite(pressures.sample).all() and np.isfinite(pressures.reference).all()):
                raise RuntimeError("kirchhoff: the solver returned non-finite pressures for {!r}".format(sample.name))
            # source by source, so that the sums over the receivers do not depend on the batch size
            for row, i in enumerate(indices):
                one = slice(row, row + 1)
                p_sample, p_reference = pressures.sample[one], pressures.reference[one]  # (1, n_receivers, n_frequencies)
                s_f[i] = scattering_freefield(p_sample, p_reference, receivers.weights)[0]
                d_sample = diffusion_coefficient(np.abs(p_sample) ** 2, receivers.weights)
                d_reference = diffusion_coefficient(np.abs(p_reference) ** 2, receivers.weights)
                d_f[i] = normalised_diffusion(d_sample, d_reference)[0]
                if i in preview:
                    slot = preview.index(i)
                    polar_sample[slot : slot + 1], polar_reference[slot : slot + 1] = _polar_levels(p_sample, p_reference, nominal)
            solver_generation = pressures.generation
            del pressures
    finally:
        batches.close()  # stops the solver's workers when a batch raised

    s_angle = band_average(s_f)
    d_angle = band_average(d_f)
    s_bands = random_incidence(s_angle, sources)
    d_bands = random_incidence(d_angle, sources)
    _, s_octaves = fold_to_octaves(s_bands, nominal)
    _, d_octaves = fold_to_octaves(d_bands, nominal)
    _, filled = fill_octaves(octaves, s_octaves)

    messages = list(sample.warnings) + list(solver.warnings(sample, nominal, exact, c))
    if nominal.max() > _ISO_TOP:
        messages.append(_BEYOND_ISO)
    messages.extend(_FILLED.format(f=f, g=g) for f, g in filled)
    for message in messages:
        _warnings.warn(message)

    generation = {
        "preset": preset,
        "band_range": [float(b) for b in band_range],
        "c": c,
        "receivers": len(receivers.directions),
        "sources": sources.n,
        "reference": sample.reference_kind,
    }
    generation.update(solver_generation)
    return ScatteringResult(
        bands=nominal.tolist(),
        s_bands=s_bands.tolist(),
        octave_bands=octaves,
        s_octaves=s_octaves.tolist(),
        filled_octaves=[f for f, _ in filled],
        s_angle=s_angle,
        source_colatitude=sources.colatitude,
        source_azimuth=sources.azimuth,
        source_weights=sources.paris_weights,
        receiver_directions=receivers.directions,
        polar_sample_db=polar_sample,
        polar_reference_db=polar_reference,
        polar_source_indices=preview,
        warnings=messages,
        generation=generation,
        name=name or sample.name,
        d_angle=d_angle,
        d_bands=d_bands.tolist(),
        d_octaves=d_octaves.tolist(),
    )
