# INTRMS   Integrated RMS-value over a frequency band.
#
# intrms(data, fs, flow, fhigh, window, noverlap)
#
#   Parameters:
#       data:       time series (raw data values)
#       fs:         sampling frequency (Hz) (default = 1)
#       flow:       low frequency limit for integration (default = 0)
#       fhigh:      high frequency limit for integration (default = Inf)
#       window:     windowing function for internal DFT calculation (default = rectangular window)
#       noverlap:   number of samples which overlap between two consecutive windows on PSD calculation
#   Returns:
#       Xrms:       integrated RMS-value in frequency domain
#       f:          frequency vector


import math
import numpy as np
from scipy import signal
from scipy import integrate


def intrms(data, fs=1, flow=0, fhigh=np.inf, window=None, noverlap=None):

    npts = data.shape[0]
    nsrcs = data.shape[1]

    if window is None:
        window = np.ones(npts, dtype=int)
    if noverlap is None:
        noverlap = math.floor(max(window.shape) / 2)

    # remove DC component
    mean = np.mean(data, axis=0)
    data -= mean

    Pxx = np.zeros((math.ceil((window.shape[0] + 1) / 2), nsrcs))
    Xrms = np.empty((Pxx.shape[0] - 1, Pxx.shape[1]))

    for src in range(nsrcs):
        # compute PSD (power spectrum density in units of power/Hz)
        f, Pxx[:, src] = signal.welch(
            data[:, src], fs, window, noverlap=noverlap, return_onesided=True
        )

        # select frequencies and PSD values within (flow, fhigh) interval
        eps = np.finfo(float).eps
        mask = (f >= flow - eps) & (f <= fhigh + eps)
        if np.sum(mask) < 2:
            f_sel = f
            Pxx_sel = Pxx[:, src]
        else:
            f_sel = f[mask]
            Pxx_sel = Pxx[mask, src]

        # frequency resolution
        df = f_sel[1] - f_sel[0]

        # integrate PSD and square root the result to get the integrated Xrms
        Xrms[:, src] = np.sqrt(df * integrate.cumtrapz(Pxx_sel))

    return Xrms, f_sel
