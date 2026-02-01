import numpy as np
import scipy
import resampy
import samplerate
import soxr
from typing import Any


# These methods were obtained from librosa.
def valid_audio(y: np.ndarray, *, mono: bool):
    if not isinstance(y, np.ndarray):
        raise Exception("Audio data must be of type numpy.ndarray")

    if not np.issubdtype(y.dtype, np.floating):
        raise Exception("Audio data must be floating-point")

    if y.ndim == 0:
        raise Exception(
            f"Audio data must be at least one-dimensional, given y.shape={y.shape}"
        )

    # if isinstance(mono, Deprecated):
    #     mono = False

    if mono and y.ndim != 1:
        raise Exception(
            f"Invalid shape for monophonic audio: ndim={y.ndim:d}, shape={y.shape}"
        )

    if not np.isfinite(y).all():
        raise Exception("Audio buffer is not finite everywhere")

    return True


def fix_length(
    data: np.ndarray, *, size: int, axis: int = -1, **kwargs: Any
) -> np.ndarray:

    kwargs.setdefault("mode", "constant")

    n = data.shape[axis]

    if n > size:
        slices = [slice(None)] * data.ndim
        slices[axis] = slice(0, size)
        return data[tuple(slices)]

    elif n < size:
        lengths = [(0, 0)] * data.ndim
        lengths[axis] = (0, size - n)
        return np.pad(data, lengths, **kwargs)

    return data



class AudioUtil:
    def __init__(self):
        pass

    def to_mono(y: np.ndarray) -> np.ndarray:
        if y.ndim > 1:
            y = np.mean(y, axis=tuple(range(y.ndim - 1)))
        return y

    def resample(
        y: np.ndarray,
        *,
        orig_sr: float,
        target_sr: float,
        res_type: str = "soxr_hq",
        fix: bool = True,
        scale: bool = False,
        axis: int = -1,
        **kwargs: Any,
    ) -> np.ndarray:

        # First, validate the audio buffer
        valid_audio(y, mono=False)

        if orig_sr == target_sr:
            return y

        ratio = float(target_sr) / orig_sr

        n_samples = int(np.ceil(y.shape[axis] * ratio))

        if res_type in ("scipy", "fft"):
            y_hat = scipy.signal.resample(y, n_samples, axis=axis)
        elif res_type == "polyphase":
            if int(orig_sr) != orig_sr or int(target_sr) != target_sr:
                raise Exception(
                    "polyphase resampling is only supported for integer-valued sampling rates."
                )

            # For polyphase resampling, we need up- and down-sampling ratios
            # We can get those from the greatest common divisor of the rates
            # as long as the rates are integrable
            orig_sr = int(orig_sr)
            target_sr = int(target_sr)
            gcd = np.gcd(orig_sr, target_sr)
            y_hat = scipy.signal.resample_poly(
                y, target_sr // gcd, orig_sr // gcd, axis=axis
            )
        elif res_type in (
            "linear",
            "zero_order_hold",
            "sinc_best",
            "sinc_fastest",
            "sinc_medium",
        ):
            # Use numpy to vectorize the resampler along the target axis
            # This is because samplerate does not support ndim>2 generally.
            y_hat = np.apply_along_axis(
                samplerate.resample, axis=axis, arr=y, ratio=ratio, converter_type=res_type
            )
        elif res_type.startswith("soxr"):
            # Use numpy to vectorize the resampler along the target axis
            # This is because soxr does not support ndim>2 generally.
            y_hat = np.apply_along_axis(
                soxr.resample,
                axis=axis,
                arr=y,
                in_rate=orig_sr,
                out_rate=target_sr,
                quality=res_type,
            )
        else:
            y_hat = resampy.resample(y, orig_sr, target_sr, filter=res_type, axis=axis)

        if fix:
            y_hat = fix_length(y_hat, size=n_samples, axis=axis, **kwargs)

        if scale:
            y_hat /= np.sqrt(ratio)

        # Match dtypes
        return np.asarray(y_hat, dtype=y.dtype)