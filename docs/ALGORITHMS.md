# Algorithms, implementation choices and limits

This is an original description of the implemented methods. Mathematical concepts
and method identifiers identify what is computed; no textbook or standard prose is
reproduced. Source citations and evidence boundaries appear in the rights inventory.

## Numerical signal path

For each channel, the core removes the arithmetic mean before AC metrics and spectra.
AC RMS is `sqrt(mean((x-mean(x))**2))`. Crest factor compares the largest absolute AC
sample with that RMS. Pearson kurtosis is the fourth standardized moment; a Gaussian
reference is approximately three, not zero. The output does not subtract three to
report excess kurtosis. Invalid/flat/clipped observations remain quality flags.

For a real FFT and window `w`, amplitude scales by the coherent window sum. One-sided
interior frequency bins are doubled, while DC and an even-length Nyquist endpoint
are not. PSD uses `fs*sum(w*w)` in its denominator. Amplitude and density therefore
have different units and should not be added indiscriminately. The implemented
windowing and normalization are in `vibration.dsp.spectrum`.

The code uses NumPy/SciPy numerical primitives rather than an external proprietary
FFT engine. Display compaction preserves representative extrema; quantitative raw
stages receive full calibrated samples. A decimated UI trace is not a measurement
input for a downstream physical integral.

Frequency-domain integration divides nonzero acceleration components by angular
frequency and excludes DC/out-of-band bins. An ideal DFT band boundary is an offline
numerical convention, not a certified analogue sensor transfer function. Sampling
aliases and unresolved nearby components cannot be recovered from a single sampled
trace without additional information.

## Bearing kinematics

For shaft frequency `fr=RPM/60`, rolling-element count `n`, diameter ratio `r=d/D` and
contact angle `theta`, let `q=r*cos(theta)`. The ideal expressions are:

- Outer-race passage: `n*fr*(1-q)/2`.
- Inner-race passage: `n*fr*(1+q)/2`.
- Cage rotation: `fr*(1-q)/2`.
- Rolling-element spin: `fr*(1-q*q)/(2*r)`.

The geometry check includes the elementary condition `d/D <= sin(pi/n)` so adjacent
elements do not overlap on the specified pitch circle. This necessary condition is
not a complete bearing design check. The model assumes a single ideal row and known
geometry; slip, load distribution, manufacturing tolerances and transfer resonances
can move or obscure observed peaks. No vendor dimensions are guessed from a part ID.

## Rotor order features

The first rotor feature schema adds power fractions around selected shaft orders and
ratios between orders/channels. Band half-width accounts for FFT-bin resolution and
a declared shaft-frequency tolerance. The extractor refuses inadequate observation
length/bandwidth rather than merging unresolved requested orders. RPM is supplied
independently of fault labels; a fault-related dominant peak is not the speed oracle.

The classifier feature contracts are versioned. Names/order/channel layout are part
of the model, not presentation labels that can be rearranged at inference time.

## Robust normal distance and persistence

Normal features use a median center and a scaled median absolute deviation, with an
explicit numerical floor to avoid division by an almost-constant feature. The score
combines standardized deviations. Its value is relative to the fitted normal domain;
it is not a calibrated probability of failure.

Window-quantile thresholds are empirical. Overlapping windows are correlated, and
their quantile is not a guarantee about per-hour plant alarms. The alarm state machine
uses observation timestamps for persistence and release, resets across episodes and
does not substitute a wall-clock sleep for measurement time.

## Gaussian diagnostic baseline

After standardization, the diagonal class score includes both squared standardized
residuals and the variance normalization term. Omitting the latter favors diffuse
classes and was corrected during development. Correcting the density expression
improved one historical benchmark but did not solve healthy-record transfer failure.
Per-class diagonal independence is a modeling assumption, not an established property
of these correlated vibration features.

## Normal-first and speed-conditioned models

The normal-first route separates anomaly screening from known-type evidence. The
RPM-conditioned route stores normal reference centers/scales at recorded nominal
speeds. Reference-fitting, calibration and fault-fitting acquisitions must be disjoint.
No extrapolation is the default. Optional bounded logarithmic-speed interpolation
adds a declared uncertainty term; that setting was not a successful substitute for
matched normal data in the recorded development experiments.

The final conditioned UOS 6204 profile used matched 8 kHz healthy acquisitions plus
separate 16 kHz source healthy records. A common 4 kHz analysis rate is obtained using
polyphase anti-alias resampling before rotor features. This common-band profile is
separate from the full-band bearing analysis path. Reducing a diagnostic band does
not validate high-frequency bearing sensing at the reduced rate.

Known faults are represented by original-acquisition prototypes. Distances are
compared by class, with novelty and margin rejection. Additional healthy data cannot
by itself prove that a fault-type library covers a new apparatus.

## Morphology fault head

`rotor_fault_morphology.v1` uses 61 features from exactly two seconds of one channel:

- Five level/shape summaries: log RMS, log crest, log Pearson kurtosis, log impulse
  factor and log normalized spectral entropy.
- Forty power fractions at half-order increments from 0.5X through 20X.
- Three summaries of half orders, harmonics and fundamental power.
- Seven fixed-band energy fractions across the common analysis bandwidth.
- Six envelope-order fractions.

Every training acquisition contributes four chronological segment medians. The
feature center/scale is derived from those representatives so a longer file does not
automatically contribute proportionally more prototypes. Class distances use the
closest representative in each class. Novelty radii are based on distances to other
original acquisitions of that class, not neighboring windows from the same file.

Development compared order-only/full-morphology modes, three RPM-distance penalties
and two margin settings. Whole-speed folds held out both sampling-rate domains for
each validation speed. The chosen model used full morphology and zero RPM penalty;
the attempted local-speed weighting was worse and was not activated. Zero margin
does not accept an exact tie or a point outside the learned class radius.

The head assumes anomaly status has already been established. It has no healthy
class and must not be run as the normal gate. Its near-perfect within-rig fault test
did not extend to the new-bearing or independent-rig data.

## Generic engineering-rule assessment

The public release has no standards-table selectors. It checks an observation's
quantity, unit, statistic, reference frame, band, duration and qualification before
comparing its canonical magnitude with caller-supplied ordered boundaries. Equality
uses the lower interval. RMS-to-peak conversion and housing-to-shaft inference are
not implicit. Results cover supplied observations only and never certify a complete
machine or authorize an automatic trip.

## What physical checks establish

Synthetic sine/mixture checks exercise known amplitude, frequency, ratios and gain
behavior. Independent motion-equation checks and numerical boundary controls target
specific physical calculations. Aliasing and finite-duration negative controls show
where information is unavailable. These checks cannot certify sensor mounting, a
new installation's fault separability, real operational FPR or remaining-life hours.
Refer to the experiment-specific reports for measured-data evidence and failures.
