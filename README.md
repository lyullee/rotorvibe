# RotorVibe

**Composable rotating-machine vibration analysis for Python.**

RotorVibe turns calibrated waveform blocks into spectra, bearing-frequency markers,
condition-relative evidence and inspectable diagnostic candidates. Use the NumPy API
inside your own application; the local web dashboard is optional.

**Alpha research release, version 0.1.0a1.** Signal calculations and bounded software
checks are documented. Fault classifiers have **not** qualified for unattended field
diagnosis: new-bearing and independent-rig transfer tests failed. No remaining-life
prediction, automatic shutdown authority or standards certification is supplied.

[한국어 설명](README.ko.md) · [User guide](docs/USER_GUIDE.md) ·
[Algorithm notes](docs/ALGORITHMS.md) · [Development record](docs/DEVELOPMENT_HISTORY.md) ·
[Continue this research](docs/CONTINUATION.md) · [Source/rights policy](docs/SOURCES_AND_RIGHTS.md)

## Install

Python 3.11+ with NumPy 2.x and SciPy 1.13+ is required.

```console
python -m pip install rotorvibe==0.1.0a1
```

For an editable checkout and verification tools:

```console
git clone https://github.com/lyullee/rotorvibe.git
cd rotorvibe
python -m pip install -e ".[verification]"
python -m unittest discover -s tests -v
```

The public facade is `rotorvibe`; the earlier `vibration` namespace remains available
so existing Python integrations can keep their imports. Raw experimental data and
trained rig-specific profiles are acquired separately, not installed by pip.

## A complete first calculation

This generated waveform verifies the API; it is not a measured fault example.

```python
import numpy as np
from rotorvibe import AnalysisConfig, SignalBlock, VibrationAnalyzer

fs = 12000
t = np.arange(fs) / fs
samples = 0.20 * np.sin(2 * np.pi * 20 * t)

analyzer = VibrationAnalyzer(AnalysisConfig(
    sample_rate_hz=fs, channels=1, unit="m/s^2",
    window_seconds=1, hop_seconds=0.25, rpm=1200,
))
result = analyzer.analyze(SignalBlock(
    samples, fs, unit="m/s^2", rpm=1200,
    channels=("drive_radial",), clock_id="daq_elapsed", episode_id="run-001",
    metadata={"asset_id": "motor-01", "condition_id": "rated_load"},
))
print(result.valid, result.metrics)
serializable = result.to_dict(include_features=False)
```

`samples` may also be an `N × C` array. A one-dimensional input represents one
channel. Supply the physical unit, channel ordering, time basis and actual asset
identity; a numeric array alone cannot establish sensor calibration or installation.

## Connect modules directly

The host controls acquisition, scheduling, storage and decisions. An analyzer instance
owns one stream; application callbacks receive the results synchronously.

```python
from rotorvibe import AnalysisConfig, VibrationAnalyzer

def receive_result(result):
    host_event_bus.publish("vibration", result.to_dict())

class MyCalculation:
    def __call__(self, result):
        return {"quality_accepted": result.valid}

analyzer = VibrationAnalyzer(
    AnalysisConfig(sample_rate_hz=12000, unit="m/s^2"),
    stages={"host_calculation": MyCalculation()},
    sinks=(receive_result,),
)
# host_event_bus is supplied by your application. No broker is imported here.
```

For streaming input, call `analyzer.push(block)` and consume the returned list of
completed windows. Gaps, sequence changes, operating identity and clock continuity
matter. `analyze(block)` handles one complete block directly. Raw-window stages can
implement `analyze_window(result, readonly_values)` to use calibrated samples instead
of a display-decimated waveform. See [composition examples](examples/python_composition.py)
and the [module catalog](docs/MODULE_CATALOG.md).

## What is implemented

| Area | Available behavior | Required evidence or boundary |
|---|---|---|
| Waveform and spectra | AC RMS, peak, crest, Pearson kurtosis, FFT amplitude, PSD, spectrogram and envelope views | Physical units, sample rate and usable sensor bandwidth |
| Bearing markers | BPFO, BPFI, FTF, BSF and 2BSF from explicit geometry or injected providers | RPM and validated bearing dimensions; ideal kinematics, no slip model |
| Normal reference | Robust feature center/scale, scope checks, relative scores and time-based alarm state | Confirmed normal records separated from threshold calibration and testing |
| Fault candidates | Gaussian baseline, normal-first diagnostics, RPM-conditioned reference bank and morphology head | Experimental; asset, channel, band, duration and speed contracts apply |
| Rule evaluation | Quantity/unit/frame contracts and caller-provided limits | **No ISO/KS limit tables are distributed**; obtain and assess rules lawfully |
| Optional service | Local HTTP, UDP ingest, SSE, SQLite history and offline UI | Start explicitly; configure authentication before non-local exposure |

### Bearing-frequency example

```python
from rotorvibe import BearingGeometry

# Illustrative geometry in a common diameter unit, not a vendor catalog entry.
bearing = BearingGeometry(rolling_elements=8, rolling_diameter=7.0,
                          pitch_diameter=35.0, contact_angle_deg=0)
print(bearing.frequencies(1200))
```

### Diagnostic states are different outcomes

`normal` means the applicable normal gate accepted the observation. `hold` means
there is no supported decision, not that the machine is healthy. `anomaly_unknown`
means deviation is detected but a trained fault type is not supported.
`fault_candidate` is a hypothesis within the model's recorded scope, not confirmation
of a physical root cause. Distances and similarity weights are not calibrated fault
probabilities. Keep `operational_use=False` for the research classifiers.

The morphology head must follow an anomaly gate. A standalone call to
`FaultDiscriminator` assumes that anomaly screening has already happened; it cannot
identify a healthy class. [A two-stage composition](examples/fault_discrimination_composition.py)
shows the ordering. No downloaded profile is silently enabled.

## Evidence: retain the failures

The following experiments have different datasets and protocols. Their percentages
must not be merged into a single product accuracy score.

| Historical experiment | Recording-level separation | Observed result | Interpretation |
|---|---|---|---|
| Brito Gaussian comparison | Fixed four-recording final split; subsequently exposed | 63.69% overall; healthy recording 0/420 | Historical reproduction, not field qualification |
| CrossSpeed supported-speed check | 24 held acquisitions after rig-specific fitting | 93.74% of 479 windows | Matched apparatus and own normal reference |
| CrossSpeed 1200 RPM transfer | 59 acquisitions / 1178 windows | 11.04%; all 399 healthy windows anomalous | Cross-speed transfer failed |
| UOS 6204 conditioned model | Eight new source files / 320 windows | 51.88% overall; fault type 48.21% | Better normal reference handling; weak type coverage |
| UOS morphology improvement | Seven new 8 kHz fault files / 560 windows | 559/560 = 99.82%; old comparator 49.11% on the same new files | Same apparatus, bearing and severities; no new healthy test |
| New UOS 30204 bearing domain | Six healthy + seven fault files; all test-only | Strict API: all hold. Offline scope-bypassed stress: healthy 240/240 anomalous, types 124/280 | Generalization failed even after scope bypass |
| Independent UFRJ ABVT rig | Fifteen healthy + fifteen fault files; all test-only | Strict API: all hold. Two predeclared amplitude assumptions: types 0/30 | Unit unresolved; no physical FPR qualification |

In the latest unadapted evaluation, 580 windows all held in the real API. Zero alerts
with zero accepted healthy observations does **not** demonstrate a zero false-alarm
rate. The offline stress route is explicitly separate from the product API and must
not be used to hide an asset mismatch. UFRJ native CSV units are not explicit in its
official page; both fixed amplitude assumptions are reported without choosing one.

The private research workspace passed 547 checks, including its licensed standards
route. That is a historical count, **not the public release's test count**. Public
release checks are recorded separately in `research/public_verification.json`; the
normative table tests are excluded and replaced with synthetic caller-rule checks.
Read [the latest external assessment](docs/EXTERNAL_BLIND_VALIDATION.rst) and
[the evidence index](research/README.md) before quoting any performance figure.

## Standards and copyright boundary

The private development project investigated ten supplied KS/ISO editions. This
public release deliberately excludes the PDFs, transcriptions, threshold lookup
tables, normative selectors and corresponding table fixtures. `vibration.iso` now
accepts an explicit `custom_rule`; it does not select an ISO machine category for you.
The example rules use invented demonstration numbers, not published standard limits.

Independent algorithm implementations, our explanatory comments and our experiment
results are released under MIT. The original external measurements, papers, vendor
catalogs and standards retain their own terms. Citation identifiers and legal license
text are intentionally preserved; third-party substantive prose and figures are not
repackaged. See [the rights inventory](docs/SOURCES_AND_RIGHTS.md).

## Optional dashboard

```console
rotorvibe-monitor --host 127.0.0.1 --port 8765
```

The service does not simulate measured validation data when no dataset is present.
Use your own live waveform input or explicitly acquired research files. Python hosts
that construct `Application` must call `close()` to stop workers and sockets.
`VIBRATION_RUNTIME_HOME` selects a writable state directory;
`VIBRATION_PROJECT_HOME` locates separately acquired datasets. Do not point these
variables at confidential data when hosting an externally reachable service.

## Reproduce, continue, cite

1. Start with synthetic core checks; they need no PDFs or raw data.
2. Use the source inventory to acquire external files under their own terms.
3. Distinguish historical replay from a new blind test: every previously opened
   recording is listed as exposed and cannot become a fresh holdout again.
4. Freeze model, preprocessing, thresholds, metadata mapping and record membership
   before opening the next holdout. Audit by original acquisition, not random windows.
5. Keep independent normal reference, calibration and final-test records. Record
   unsupported coverage and false negatives as well as correct classifications.

[Continuation instructions](docs/CONTINUATION.md) identify exact commands, preserved
artifacts, unavailable private components, model hashes and next validation needs.
The archive DOI is [10.5281/zenodo.23937890](https://doi.org/10.5281/zenodo.23937890);
use `CITATION.cff` for software citation. A DOI identifies an archived release; it
does not certify a diagnostic model.

Copyright © 2026 Ugwiyeon Lee. Original software: [MIT](LICENSE).
